import os
import re
import threading
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import SmsVerificationRecord

SCENE_TEMPLATES = {
    'register': os.getenv('ALIYUN_SMS_TEMPLATE_REGISTER', '100001'),
    'login': os.getenv('ALIYUN_SMS_TEMPLATE_LOGIN', '100001'),
    'modify_phone': os.getenv('ALIYUN_SMS_TEMPLATE_MODIFY_PHONE', '100002'),
    'reset_password': os.getenv('ALIYUN_SMS_TEMPLATE_RESET_PASSWORD', '100003'),
    'bind_phone': os.getenv('ALIYUN_SMS_TEMPLATE_BIND_PHONE', '100004'),
    'verify_phone': os.getenv('ALIYUN_SMS_TEMPLATE_VERIFY_PHONE', '100005'),
}
SMS_VALID_SECONDS = 300
SMS_SEND_INTERVAL_SECONDS = 60
SMS_CODE_LENGTH = 6
SMS_TEMPLATE_PARAM = '{"code":"##code##","min":"5"}'

# The provider also enforces its 60-second interval. This lock prevents two
# requests handled by the same worker from passing the local preflight together.
_send_lock = threading.Lock()
ERROR_MESSAGES = {
    'MOBILE_NUMBER_ILLEGAL': '手机号格式不正确',
    'BUSINESS_LIMIT_CONTROL': '发送次数超限，请明天再试',
    'BIZ.LIMIT': '发送次数超限，请明天再试',
    'FREQUENCY_FAIL': '发送太频繁，请稍后再试',
    'biz.FREQUENCY': '发送太频繁，请稍后再试',
    'check frequency failed': '发送太频繁，请稍后再试',
}


def _validate_phone(phone: str) -> str:
    phone = str(phone or '').strip()
    if not re.fullmatch(r'1[3-9]\d{9}', phone):
        raise ValueError('手机号格式不正确')
    return phone


class SmsServiceError(RuntimeError):
    """A safe message that may be returned to the caller."""


def _client():
    try:
        from alibabacloud_dypnsapi20170525.client import Client
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError as exc:
        raise SmsServiceError('短信服务暂不可用，请联系管理员') from exc
    access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID', '')
    access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET', '')
    if not access_key_id or not access_key_secret:
        raise SmsServiceError('短信服务尚未配置，请联系管理员')
    config = open_api_models.Config(access_key_id=access_key_id, access_key_secret=access_key_secret)
    config.endpoint = os.getenv('ALIYUN_DYPNS_ENDPOINT', 'dypnsapi.aliyuncs.com')
    return Client(config)


def _friendly_error(error: Exception, *, checking: bool = False) -> SmsServiceError:
    text = ' '.join(
        str(part) for part in (
            getattr(error, 'code', ''),
            getattr(error, 'message', ''),
            str(error),
        ) if part
    )
    lower_text = text.lower()
    for key, message in ERROR_MESSAGES.items():
        if key.lower() in lower_text:
            return SmsServiceError(message)
    return SmsServiceError('验证码校验失败，请稍后再试' if checking else '短信发送失败，请稍后再试')


def _response_field(value, field: str, default=None):
    """Read SDK 2.0.0 response models and test doubles alike."""

    if isinstance(value, dict):
        return value.get(field, value.get(''.join(part.title() for part in field.split('_')), default))
    return getattr(value, field, default)


def _provider_out_id(record: SmsVerificationRecord) -> Optional[str]:
    """Older rows stored Aliyun RequestId, not our external OutId."""

    value = record.request_id or ''
    return value if re.fullmatch(r'[0-9a-f]{32}', value) else None


def send_sms(db: Session, phone: str, scene: str) -> dict:
    phone = _validate_phone(phone)
    template_code = SCENE_TEMPLATES.get(scene)
    if not template_code:
        raise ValueError('短信场景不支持')
    with _send_lock:
        last = db.scalar(select(SmsVerificationRecord).where(
            SmsVerificationRecord.phone == phone,
            SmsVerificationRecord.sent_at >= datetime.utcnow() - timedelta(seconds=SMS_SEND_INTERVAL_SECONDS),
            SmsVerificationRecord.sent_at <= datetime.utcnow(),
        ).order_by(SmsVerificationRecord.sent_at.desc()))
        db.rollback()
        if last:
            raise SmsServiceError('发送太频繁，请稍后再试')
        try:
            from alibabacloud_dypnsapi20170525 import models as dypns_models
            out_id = uuid4().hex
            request = dypns_models.SendSmsVerifyCodeRequest(
                phone_number=phone,
                out_id=out_id,
                sign_name=os.getenv('ALIYUN_SMS_SIGN_NAME', '速通互联验证码'),
                template_code=template_code,
                template_param=SMS_TEMPLATE_PARAM,
                code_length=SMS_CODE_LENGTH,
                valid_time=SMS_VALID_SECONDS,
                interval=SMS_SEND_INTERVAL_SECONDS,
                code_type=1,
            )
            response = _client().send_sms_verify_code(request)
            body = _response_field(response, 'body')
            model = _response_field(body, 'model')
            # SDK responses normally include ``Success=true`` and ``Model``.
            # Some compatible gateways omit the optional Success field, so a
            # present model is enough unless Success is explicitly false.
            if model is None or _response_field(body, 'success') is False:
                code = _response_field(body, 'code', '') or ''
                message = _response_field(body, 'message', '') or ''
                raise _friendly_error(RuntimeError(f'{code} {message}'))
            # Keep the external ID in the existing request_id column. The
            # provider's RequestId is only a trace ID and cannot scope checks.
            record = SmsVerificationRecord(
                phone=phone,
                scene=scene,
                request_id=out_id,
                sent_at=datetime.utcnow(),
                status='SENT',
            )
            db.add(record)
            db.commit()
            return {'message': '验证码已发送'}
        except SmsServiceError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise _friendly_error(exc) from exc


def check_sms_code(db: Session, phone: str, code: str, scene: str) -> bool:
    phone = _validate_phone(phone)
    if scene not in SCENE_TEMPLATES:
        raise ValueError('短信场景不支持')
    if not re.fullmatch(rf'\d{{{SMS_CODE_LENGTH}}}', str(code or '')):
        return False
    cutoff = datetime.utcnow() - timedelta(seconds=SMS_VALID_SECONDS)
    query = select(SmsVerificationRecord).where(
        SmsVerificationRecord.phone == phone,
        SmsVerificationRecord.status == 'SENT',
        SmsVerificationRecord.sent_at >= cutoff,
        SmsVerificationRecord.sent_at <= datetime.utcnow(),
    )
    query = query.where(SmsVerificationRecord.scene == scene)
    pending = db.scalar(query.order_by(SmsVerificationRecord.sent_at.desc(), SmsVerificationRecord.id.desc()))
    if not pending:
        db.rollback()
        return False
    pending_id = pending.id
    pending_out_id = _provider_out_id(pending)
    # Do not hold a database transaction while waiting for Alibaba Cloud.
    # The conditional UPDATE below rechecks status and expiry afterwards.
    db.rollback()
    try:
        from alibabacloud_dypnsapi20170525 import models as dypns_models
        request = dypns_models.CheckSmsVerifyCodeRequest(
            phone_number=phone,
            out_id=pending_out_id,
            verify_code=str(code),
        )
        response = _client().check_sms_verify_code(request)
        body = _response_field(response, 'body')
        model = _response_field(body, 'model')
        # Alibaba's documented success criterion is Model.VerifyResult ==
        # PASS. Treat an explicit Success=false as a provider failure, but do
        # not reject a valid PASS result merely because an SDK/test response
        # omits the optional Success field.
        if body is None or model is None:
            raise _friendly_error(RuntimeError('missing verification response'), checking=True)
        if _response_field(body, 'success') is False:
            error = RuntimeError(f"{_response_field(body, 'code', '')} {_response_field(body, 'message', '')}")
            raise _friendly_error(error, checking=True)
        verify_result = _response_field(model, 'verify_result', '')
        passed = verify_result == 'PASS'
        if passed:
            # Compare-and-swap makes only one concurrent caller own this proof.
            # A later route consumes VERIFIED after completing its action.
            claimed = db.execute(
                update(SmsVerificationRecord)
                .where(
                    SmsVerificationRecord.id == pending_id,
                    SmsVerificationRecord.status == 'SENT',
                    SmsVerificationRecord.sent_at >= datetime.utcnow() - timedelta(seconds=SMS_VALID_SECONDS),
                    SmsVerificationRecord.sent_at <= datetime.utcnow(),
                )
                .values(status='VERIFIED', verified_at=datetime.utcnow())
            )
            if claimed.rowcount != 1:
                db.rollback()
                return False
            db.commit()
        else:
            db.rollback()
        return passed
    except SmsServiceError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise _friendly_error(exc, checking=True) from exc
