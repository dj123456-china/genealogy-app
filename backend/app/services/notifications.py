"""服务端纪念日调度、持久去重和可选 Web Push 投递。"""
from __future__ import annotations
import asyncio
from datetime import date, datetime, timedelta
import json
import logging
import os
import re
import hashlib
from zoneinfo import ZoneInfo
from types import SimpleNamespace

from lunar_python import Lunar, Solar
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Family, FamilyMembership, NotificationRecord, Reminder, User, SchedulerCheckpoint

logger = logging.getLogger(__name__)
CHINA = ZoneInfo('Asia/Shanghai')


def utc_now() -> datetime:
    return datetime.utcnow()


def reminder_occurrences(reminder: Reminder, today: date) -> list[date]:
    """返回今天附近的真实纪念日；2 月 29 日和不存在的闰农历日跳过。"""
    try:
        source = date.fromisoformat(reminder.date)
    except (ValueError, TypeError):
        return []
    if reminder.repeat != '每年':
        return [source]
    occurrences = []
    source_year = Solar.fromYmd(source.year, source.month, source.day).getLunar().getYear() if reminder.calendar == 'lunar' else source.year
    for year in range(max(source_year, today.year - 1), today.year + 2):
        try:
            if reminder.calendar == 'qingming':
                solar = Solar.fromYmd(year, 4, 5).getLunar().getJieQiTable()['清明']
                occurrence = date.fromisoformat(solar.toYmd())
            elif reminder.calendar == 'lunar':
                if not reminder.lunar_month or not reminder.lunar_day:
                    continue
                month = -reminder.lunar_month if reminder.lunar_leap else reminder.lunar_month
                solar = Lunar.fromYmd(year, month, reminder.lunar_day).getSolar()
                # 对无效农历日不允许库自动溢出。
                lunar = solar.getLunar()
                if lunar.getYear() != year or lunar.getMonth() != month or lunar.getDay() != reminder.lunar_day:
                    continue
                occurrence = date.fromisoformat(solar.toYmd())
            else:
                occurrence = date(year, source.month, source.day)
        except Exception:
            # lunar-python 对不存在的闰月/日期使用普通 Exception。
            continue
        if occurrence >= source:
            occurrences.append(occurrence)
    return occurrences


def advance_days(value: str) -> int:
    if value == '当天':
        return 0
    match = re.fullmatch(r'提前\s*(\d+)\s*天', value or '')
    return min(365, int(match.group(1))) if match else 0


def reminder_fingerprint(reminder) -> str:
    values = {key: getattr(reminder, key, None) for key in
              ['family_id', 'member_id', 'title', 'type', 'date', 'advance', 'repeat', 'calendar', 'lunar_month', 'lunar_day', 'lunar_leap']}
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate_notifications(db: Session, now: datetime | None = None) -> int:
    """无需客户端启动，周期执行后将提醒写入收件箱；唯一键防重启/多 worker 重复。"""
    now = now or datetime.now(CHINA)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CHINA)
    today = now.astimezone(CHINA).date()
    checkpoint = db.get(SchedulerCheckpoint, 'reminders')
    start = today
    if checkpoint:
        # 从上次成功处理日的下一天开始补偿，避免停机跨过提醒日后永久漏发。
        start = max(date.fromisoformat(checkpoint.processed_on) + timedelta(days=1), today - timedelta(days=7))
        start = min(start, today)
    created = 0
    day = start
    while day <= today:
        created += _generate_day(db, day, today)
        day += timedelta(days=1)
    if not checkpoint:
        try:
            with db.begin_nested():
                db.add(SchedulerCheckpoint(name='reminders', processed_on=today.isoformat()))
                db.flush()
        except IntegrityError:
            pass
    from sqlalchemy import update
    db.execute(update(SchedulerCheckpoint).where(SchedulerCheckpoint.name == 'reminders',
        SchedulerCheckpoint.processed_on < today.isoformat()).values(processed_on=today.isoformat()))
    db.commit()
    return created


def _generate_day(db: Session, today: date, actual_today: date) -> int:
    created = 0
    for reminder in db.scalars(select(Reminder)):
        family = db.get(Family, reminder.family_id)
        if not family:
            continue
        recipients = {family.owner_id, *db.scalars(select(FamilyMembership.user_id).where(
            FamilyMembership.family_id == family.id))}
        offset = advance_days(reminder.advance)
        stages = {0, offset}
        for occurrence in reminder_occurrences(reminder, today):
            for days in stages:
                if occurrence - timedelta(days=days) != today:
                    continue
                for user_id in recipients:
                    user = db.get(User, user_id)
                    if not user or not user.notifications_enabled:
                        continue
                    event = f'r{reminder.id}'
                    if reminder.member_id and reminder.type in {'birthday', 'memorial', '生日', '忌日'}:
                        kind = 'birthday' if reminder.type in {'birthday', '生日'} else 'memorial'
                        event = f'm{reminder.member_id}:{kind}'
                    key = f'{user_id}:{event}:{occurrence.isoformat()}:{days}'
                    if db.scalar(select(NotificationRecord.id).where(NotificationRecord.dedupe_key == key)):
                        continue
                    description = f'今天是{reminder.title}' if not days else f'{days} 天后是{reminder.title}'
                    late = today < actual_today
                    if late:
                        description = f'补记 {today.isoformat()} 的提醒：{reminder.title}（仅补入收件箱）'
                    record = NotificationRecord(user_id=user_id, family_id=family.id, reminder_id=reminder.id,
                        title=reminder.title, body=f'{family.name}：{description}（{occurrence.isoformat()}）。',
                        due_date=occurrence.isoformat(), dedupe_key=key, channel='in_app', status='SENT',
                        source_fingerprint='catchup' if late else reminder_fingerprint(reminder),
                        sent_at=utc_now(), push_status='PENDING' if user.system_notifications_enabled and not late else 'DISABLED',
                        mobile_status='PENDING' if user.system_notifications_enabled and not late else 'DISABLED')
                    # 唯一约束竞争只跳过这一条，不丢掉本轮其他用户的通知。
                    try:
                        with db.begin_nested():
                            db.add(record)
                            db.flush()
                        created += 1
                    except IntegrityError:
                        pass
    db.commit()
    return created


def push_configuration() -> dict:
    public_key = os.getenv('WEB_PUSH_VAPID_PUBLIC_KEY', '')
    private_key = os.getenv('WEB_PUSH_VAPID_PRIVATE_KEY', '')
    subject = os.getenv('WEB_PUSH_VAPID_SUBJECT', '')
    configured = bool(public_key and private_key and subject)
    error = None
    if configured:
        try:
            import base64
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from py_vapid import Vapid
            vapid = Vapid.from_file(private_key) if os.path.isfile(private_key) else Vapid.from_string(private_key)
            actual = base64.urlsafe_b64encode(vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).decode().rstrip('=')
            if actual != public_key.rstrip('=') or not subject.startswith(('mailto:', 'https://')):
                raise ValueError('公私钥或联系地址不匹配')
        except Exception:
            configured = False
            error = 'VAPID 密钥格式、公私钥匹配或联系地址配置有误，请检查服务端设置。'
    return {'configured': configured, 'public_key': public_key if configured else None,
            'private_key': private_key, 'subject': subject, 'error': error}


def delivery_status(db: Session, user: User) -> dict:
    from app.services.wechat_push import status as wechat_status
    from app.models.user import PushSubscription
    configuration = push_configuration()
    from app.services.mobile_push import mobile_configuration
    from app.models.user import MobilePushDevice, UserSession
    mobile = mobile_configuration()
    active_sessions = select(UserSession.id).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > utc_now())
    devices = len(list(db.scalars(select(MobilePushDevice.id).where(MobilePushDevice.user_id == user.id, MobilePushDevice.session_id.in_(active_sessions)))))
    scheduler_enabled = os.getenv('NOTIFICATION_SCHEDULER_ENABLED', 'true').lower() not in {'false', '0', 'no'}
    subscriptions = len(list(db.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user.id, PushSubscription.session_id.in_(active_sessions)))))
    return {
        'in_app': {'supported': True, 'configured': scheduler_enabled, 'enabled': user.notifications_enabled and scheduler_enabled,
                   'message': '服务端定时生成通知并保存在收件箱，前端关闭后仍会生成。' if scheduler_enabled
                   else '后台纪念日调度已关闭，不会自动生成新通知；已有通知仍可查看。'},
        'browser': {'supported': True, 'configured': True, 'enabled': user.system_notifications_enabled,
                    'message': '浏览器授权后可在页面运行时显示系统通知。'},
        'web_push': {'supported': True, 'configured': configuration['configured'],
                     'enabled': user.system_notifications_enabled and user.notifications_enabled,
                     'subscriptions': subscriptions, 'public_key': configuration['public_key'],
                     'message': '已配置 Web Push；需在 HTTPS 或 localhost 浏览器授权并登记设备。' if configuration['configured']
                     else configuration['error'] or '尚未配置 WEB_PUSH_VAPID 密钥；关闭页面后的推送尚未启用。'},
        'mobile_push': {'supported': True, 'configured': mobile['configured'],
                        'enabled': user.notifications_enabled and user.system_notifications_enabled,
                        'devices': devices, 'provider': 'UniPush 2',
                        'message': '已配置 UniPush 2；需原生 App 登记 client ID，并在供应商控制台配置厂商/APNs 通道。'
                        if mobile['configured'] else '尚未配置 UNIPUSH_APP_ID / APP_KEY / MASTER_SECRET，App 后台推送未启用。'},
        'timezone': 'Asia/Shanghai',
        'wechat_push': wechat_status(db, user),
    }


def send_web_push(subscription, record: NotificationRecord, configuration: dict) -> None:
    from pywebpush import webpush
    webpush(subscription_info={'endpoint': subscription.endpoint,
            'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth}},
            data=json.dumps({'id': record.id, 'title': record.title, 'body': record.body,
                             'url': '/#/pages/index/index?notifications=1'}, ensure_ascii=False),
            vapid_private_key=configuration['private_key'],
            vapid_claims={'sub': configuration['subject']}, ttl=86400, timeout=10)


def deliver_pending_push(db: Session, now: datetime | None = None) -> int:
    from app.models.user import PushSubscription, UserSession
    from app.services.notification_access import can_receive_family_notification
    configuration = push_configuration()
    if not configuration['configured']:
        return 0
    now = now or utc_now()
    eligible_devices = select(PushSubscription.user_id).join(UserSession, PushSubscription.session_id == UserSession.id).where(
        UserSession.user_id == PushSubscription.user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
    delivered = 0
    records = db.scalars(select(NotificationRecord).where(
        NotificationRecord.created_at >= now - timedelta(days=2),
        # 未登记设备的旧通知不能占满批次，阻塞其他用户的新提醒。
        NotificationRecord.user_id.in_(eligible_devices),
        or_(NotificationRecord.push_status.in_(['PENDING', 'NO_SUBSCRIPTION']),
            (NotificationRecord.push_status == 'FAILED') &
            (NotificationRecord.push_attempted_at < now - timedelta(minutes=15)),
            (NotificationRecord.push_status == 'SENDING') &
            (NotificationRecord.push_attempted_at < now - timedelta(minutes=5))))
        .order_by(NotificationRecord.id).limit(100))
    for record in records:
        user = db.get(User, record.user_id)
        if not user or not user.notifications_enabled or not user.system_notifications_enabled:
            record.push_status = 'DISABLED'
            continue
        if not can_receive_family_notification(db, record):
            record.push_status = 'CANCELLED'
            db.commit()
            continue
        subscriptions = list(db.scalars(select(PushSubscription).join(UserSession, PushSubscription.session_id == UserSession.id).where(
            PushSubscription.user_id == user.id, UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)))
        if not subscriptions:
            record.push_status = 'NO_SUBSCRIPTION'
            continue
        targets = [(subscription, SimpleNamespace(id=subscription.id, session_id=subscription.session_id,
                    endpoint=subscription.endpoint, p256dh=subscription.p256dh, auth=subscription.auth)) for subscription in subscriptions]
        # 先占有投递，避免多个 scheduler 对同一条消息同时发送。
        from sqlalchemy import update
        previous = record.push_status
        previous_attempt = record.push_attempted_at
        claimed = db.execute(update(NotificationRecord).where(NotificationRecord.id == record.id,
            NotificationRecord.push_status == previous, NotificationRecord.push_attempted_at == previous_attempt)
            .values(push_status='SENDING', push_attempted_at=now))
        db.commit()
        if claimed.rowcount != 1:
            continue
        successes = 0
        errors = []
        cancelled = False
        attempted = 0
        for subscription, target in targets:
            if not can_receive_family_notification(db, record):
                cancelled = True
                break
            valid = db.scalar(select(PushSubscription.id).join(UserSession, PushSubscription.session_id == UserSession.id).where(
                PushSubscription.id == target.id, PushSubscription.user_id == record.user_id, PushSubscription.session_id == target.session_id,
                UserSession.user_id == record.user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > utc_now()))
            if not valid:
                continue
            attempted += 1
            try:
                send_web_push(target, record, configuration)
                successes += 1
            except Exception as exc:
                response = getattr(exc, 'response', None)
                if response is not None and getattr(response, 'status_code', None) in (404, 410):
                    db.delete(subscription)
                # 只记录类型和 HTTP 状态，供应商异常可能包含凭证/设备 endpoint。
                code = getattr(response, 'status_code', None) if response is not None else None
                errors.append(f'{type(exc).__name__}' + (f' HTTP {code}' if code else ''))
        record.push_attempted_at = now
        record.push_status = 'CANCELLED' if cancelled else 'NO_SUBSCRIPTION' if not attempted else 'SENT' if successes and not errors else 'PARTIAL' if successes else 'FAILED'
        record.push_error = '; '.join(errors)[:500] or None
        delivered += int(successes > 0)
        db.commit()
    return delivered


def notification_tick():
    with SessionLocal() as db:
        generate_notifications(db)
        deliver_pending_push(db)
        from app.services.mobile_push import deliver_pending_mobile
        deliver_pending_mobile(db)
        from app.services.wechat_push import deliver as deliver_wechat
        deliver_wechat(db)


async def notification_scheduler(stop: asyncio.Event):
    while not stop.is_set():
        try:
            await asyncio.to_thread(notification_tick)
        except Exception:
            logger.exception('纪念日通知调度失败，将在下一轮重试')
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass
