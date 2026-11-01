from datetime import datetime
import hashlib
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import bearer, get_current_user
from app.core.security import token_fingerprint
from app.db.session import get_db
from app.models import NotificationRecord, User, UserSession
from app.services.notifications import delivery_status, push_configuration

router = APIRouter(prefix='/notifications', tags=['通知'])


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=80, max_length=200)
    auth: str = Field(min_length=16, max_length=100)

    @field_validator('p256dh', 'auth')
    @classmethod
    def base64_key(cls, value, info):
        import base64
        import binascii
        try:
            decoded = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
        except (binascii.Error, ValueError) as exc:
            raise ValueError('设备推送密钥格式不正确') from exc
        if len(decoded) != (65 if info.field_name == 'p256dh' else 16):
            raise ValueError('设备推送密钥长度不正确')
        return value


class SubscriptionPayload(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: PushKeys

    @field_validator('endpoint')
    @classmethod
    def valid_endpoint(cls, value):
        parsed = urlparse(value)
        # 推送订阅来自浏览器厂商，禁止私网/本机 endpoint 被调度器请求。
        providers = ('fcm.googleapis.com', 'updates.push.services.mozilla.com',
                     'web.push.apple.com', 'notify.windows.com', 'push.services.mozilla.com')
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError('推送地址必须是安全 HTTPS 地址')
        if not any(host == provider or host.endswith('.' + provider) for provider in providers):
            raise ValueError('推送地址须由受支持的浏览器推送服务提供')
        return value


@router.get('/delivery-status')
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return delivery_status(db, user)


@router.get('')
def inbox(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = db.scalars(select(NotificationRecord).where(NotificationRecord.user_id == user.id,
        NotificationRecord.channel == 'in_app').order_by(NotificationRecord.created_at.desc(),
        NotificationRecord.id.desc()).limit(200))
    return [{'id': record.id, 'family_id': record.family_id, 'title': record.title, 'body': record.body,
             'read_at': record.read_at.isoformat() + 'Z' if record.read_at else None,
             'created_at': record.created_at.isoformat() + 'Z', 'reminder_id': record.reminder_id,
             'push_status': record.push_status, 'mobile_status': record.mobile_status} for record in records]


@router.patch('/{notification_id}/read')
def mark_read(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.get(NotificationRecord, notification_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail='通知不存在')
    record.read_at = record.read_at or datetime.utcnow()
    db.commit()
    return {'id': record.id, 'read_at': record.read_at.isoformat() + 'Z'}


@router.post('/read-all')
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = db.execute(update(NotificationRecord).where(NotificationRecord.user_id == user.id,
        NotificationRecord.read_at.is_(None)).values(read_at=datetime.utcnow()))
    db.commit()
    return {'message': '已标记全部通知为已读', 'count': result.rowcount}


@router.post('/subscriptions', status_code=201)
def subscribe(payload: SubscriptionPayload, user: User = Depends(get_current_user), credentials=Depends(bearer), db: Session = Depends(get_db)):
    from app.models.user import PushSubscription
    if not push_configuration()['configured']:
        raise HTTPException(status_code=503, detail='尚未配置 Web Push 密钥，后台推送暂不可用')
    fingerprint = hashlib.sha256(payload.endpoint.encode()).hexdigest()
    subscription = db.scalar(select(PushSubscription).where(PushSubscription.endpoint_hash == fingerprint))
    if subscription:
        # 同一浏览器从一个账号切换到另一个账号，更新归属，不能继续投递旧账号资料。
        subscription.user_id = user.id
        subscription.p256dh = payload.keys.p256dh
        subscription.auth = payload.keys.auth
    else:
        subscription = PushSubscription(user_id=user.id, endpoint=payload.endpoint, endpoint_hash=fingerprint,
            p256dh=payload.keys.p256dh, auth=payload.keys.auth)
        db.add(subscription)
    subscription.session_id = db.scalar(select(UserSession.id).where(UserSession.token_hash == token_fingerprint(credentials.credentials)))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='设备登记发生并发冲突，请重试') from exc
    return {'id': subscription.id, 'message': '当前设备已登记后台推送'}


@router.delete('/subscriptions/{subscription_id}')
def unsubscribe(subscription_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.user import PushSubscription
    subscription = db.get(PushSubscription, subscription_id)
    if not subscription or subscription.user_id != user.id:
        raise HTTPException(status_code=404, detail='设备订阅不存在')
    db.delete(subscription)
    db.commit()
    return {'message': '当前设备已取消后台推送'}


class MobileDevicePayload(BaseModel):
    client_id: str = Field(min_length=8, max_length=256, pattern=r'^[A-Za-z0-9_-]+$')
    platform: str = Field(pattern=r'^(android|ios)$')


@router.post('/mobile-devices', status_code=201)
def register_mobile_device(payload: MobileDevicePayload, user: User = Depends(get_current_user), credentials=Depends(bearer), db: Session = Depends(get_db)):
    from app.models.user import MobilePushDevice
    from app.services.mobile_push import mobile_configuration
    if not mobile_configuration()['configured']:
        raise HTTPException(status_code=503, detail='尚未配置 UniPush 2，App 后台推送暂不可用')
    fingerprint = hashlib.sha256(payload.client_id.encode()).hexdigest()
    device = db.scalar(select(MobilePushDevice).where(MobilePushDevice.client_hash == fingerprint))
    if device:
        device.user_id = user.id
        device.platform = payload.platform
    else:
        device = MobilePushDevice(user_id=user.id, client_id=payload.client_id,
            client_hash=fingerprint, platform=payload.platform)
        db.add(device)
    device.session_id = db.scalar(select(UserSession.id).where(UserSession.token_hash == token_fingerprint(credentials.credentials)))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='设备登记发生并发冲突，请重试') from exc
    return {'id': device.id, 'message': '当前 App 设备已登记 UniPush 2 后台推送'}


@router.delete('/mobile-devices/{device_id}')
def unregister_mobile_device(device_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.user import MobilePushDevice
    device = db.get(MobilePushDevice, device_id)
    if not device or device.user_id != user.id:
        raise HTTPException(status_code=404, detail='设备登记不存在')
    db.delete(device)
    db.commit()
    return {'message': '当前 App 设备已取消后台推送'}
