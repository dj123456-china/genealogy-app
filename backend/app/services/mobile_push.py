"""UniPush 2/Getui v2 的真实 HTTP 适配；无凭证时不调用供应商。"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import os
import threading
import time
from types import SimpleNamespace

import requests
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import NotificationRecord, User

_TOKEN_CACHE = {}
_TOKEN_LOCK = threading.Lock()


class ProviderError(RuntimeError):
    def __init__(self, code):
        super().__init__(f'UniPush 供应商拒绝请求（code={code}）')
        self.code = code


def mobile_configuration() -> dict:
    values = {key: os.getenv('UNIPUSH_' + key.upper(), '') for key in ('app_id', 'app_key', 'master_secret')}
    values['configured'] = bool(all(values.values()))
    values['base_url'] = os.getenv('UNIPUSH_API_BASE', 'https://restapi.getui.com/v2').rstrip('/')
    return values


def _provider_request(url: str, payload: dict, *, headers: dict | None = None) -> dict:
    response = requests.post(url, json=payload, headers=headers or {}, timeout=10)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or result.get('code') != 0:
        code = result.get('code') if isinstance(result, dict) else 'invalid_response'
        raise ProviderError(code)
    return result


def provider_token(configuration: dict, force: bool = False) -> str:
    key = (configuration['app_id'], configuration['app_key'], configuration['master_secret'])
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if not force and cached and cached['expires_at'] > time.time() + 60:
            return cached['token']
        timestamp = str(int(time.time() * 1000))
        sign = hashlib.sha256((configuration['app_key'] + timestamp + configuration['master_secret']).encode()).hexdigest()
        result = _provider_request(f"{configuration['base_url']}/{configuration['app_id']}/auth",
                                   {'sign': sign, 'timestamp': timestamp, 'appkey': configuration['app_key']})
        data = result.get('data') or {}
        token = data.get('token')
        if not token:
            raise RuntimeError('UniPush 供应商未返回认证令牌')
        try:
            expires = int(data.get('expire_time', 0)) / 1000
        except (ValueError, TypeError):
            expires = 0
        _TOKEN_CACHE[key] = {'token': token, 'expires_at': expires or time.time() + 3600}
        return token


def send_mobile_push(device, record: NotificationRecord, configuration: dict) -> dict:
    if not configuration['configured']:
        raise RuntimeError('尚未配置 UniPush 2')
    token = provider_token(configuration)
    request_id = hashlib.sha256(f'family:{record.id}:{device.client_id}'.encode()).hexdigest()[:32]
    title, body = record.title, record.body
    payload = {
        'request_id': request_id,
        'settings': {'ttl': 86400000},
        'audience': {'cid': [device.client_id]},
        'push_message': {'notification': {'title': title, 'body': body, 'click_type': 'startapp'}},
        'push_channel': {
            'android': {'ups': {'notification': {'title': title, 'body': body, 'click_type': 'startapp'}}},
            'ios': {'type': 'notify', 'aps': {'alert': {'title': title, 'body': body}, 'sound': 'default'}},
        },
    }
    # code=0 证明供应商接受投递，不等于用户设备已经收到。
    url = f"{configuration['base_url']}/{configuration['app_id']}/push/single/cid"
    try:
        return _provider_request(url, payload, headers={'token': token})
    except ProviderError as exc:
        if exc.code != 10001:
            raise
        # 供应商可能提前撤销 token，重新鉴权后只重试一次。
        token = provider_token(configuration, force=True)
        return _provider_request(url, payload, headers={'token': token})


def deliver_pending_mobile(db: Session, now: datetime | None = None) -> int:
    from app.models.user import MobilePushDevice, UserSession
    from app.services.notification_access import can_receive_family_notification
    configuration = mobile_configuration()
    if not configuration['configured']:
        return 0
    now = now or datetime.utcnow()
    eligible_devices = select(MobilePushDevice.user_id).join(UserSession, MobilePushDevice.session_id == UserSession.id).where(
        UserSession.user_id == MobilePushDevice.user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
    accepted = 0
    records = db.scalars(select(NotificationRecord).where(NotificationRecord.created_at >= now - timedelta(days=2),
        NotificationRecord.user_id.in_(eligible_devices),
        or_(NotificationRecord.mobile_status.in_(['PENDING', 'NO_DEVICE']),
            (NotificationRecord.mobile_status == 'FAILED') & (NotificationRecord.mobile_attempted_at < now - timedelta(minutes=15)),
            (NotificationRecord.mobile_status == 'SENDING') & (NotificationRecord.mobile_attempted_at < now - timedelta(minutes=5))))
        .order_by(NotificationRecord.id).limit(100))
    for record in records:
        user = db.get(User, record.user_id)
        if not user or not user.notifications_enabled or not user.system_notifications_enabled:
            record.mobile_status = 'DISABLED'
            continue
        if not can_receive_family_notification(db, record):
            record.mobile_status = 'CANCELLED'
            db.commit()
            continue
        devices = list(db.scalars(select(MobilePushDevice).join(UserSession, MobilePushDevice.session_id == UserSession.id).where(
            MobilePushDevice.user_id == user.id, UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)))
        if not devices:
            record.mobile_status = 'NO_DEVICE'
            continue
        targets = [SimpleNamespace(id=device.id, session_id=device.session_id, client_id=device.client_id, platform=device.platform) for device in devices]
        claimed = db.execute(update(NotificationRecord).where(NotificationRecord.id == record.id,
            NotificationRecord.mobile_status == record.mobile_status,
            NotificationRecord.mobile_attempted_at == record.mobile_attempted_at)
            .values(mobile_status='SENDING', mobile_attempted_at=now))
        db.commit()
        if claimed.rowcount != 1:
            continue
        successes = 0
        errors = []
        cancelled = False
        attempted = 0
        for device in targets:
            if not can_receive_family_notification(db, record):
                cancelled = True
                break
            valid = db.scalar(select(MobilePushDevice.id).join(UserSession, MobilePushDevice.session_id == UserSession.id).where(
                MobilePushDevice.id == device.id, MobilePushDevice.user_id == record.user_id, MobilePushDevice.session_id == device.session_id,
                UserSession.user_id == record.user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > datetime.utcnow()))
            if not valid:
                continue
            attempted += 1
            try:
                send_mobile_push(device, record, configuration)
                successes += 1
            except Exception as exc:
                errors.append(type(exc).__name__)
        record.mobile_attempted_at = now
        record.mobile_status = 'CANCELLED' if cancelled else 'NO_DEVICE' if not attempted else 'ACCEPTED' if successes and not errors else 'PARTIAL' if successes else 'FAILED'
        record.mobile_error = '; '.join(errors)[:500] or None
        db.commit()
        accepted += int(successes > 0)
    return accepted
