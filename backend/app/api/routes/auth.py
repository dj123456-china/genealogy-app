from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import bearer, get_current_user
from app.core.security import (
    create_access_token,
    create_registration_token,
    decode_registration_token,
    hash_password,
    verify_password,
    decode_access_token,
    token_fingerprint,
)
from app.db.session import get_db
from app.models.user import LoginLog, SmsVerificationRecord, User, UserSession
from app.schemas.auth import (
    BindPhoneRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    SendSmsRequest,
    SmsLoginRequest,
    SmsLoginResponse,
    TokenResponse,
    UserOut,
    PreferencesRequest,
)
from app.services.sms import check_sms_code, send_sms
from app.services.accounts import audit, delete_user_data, revoke_device_subscriptions

router = APIRouter(prefix='/auth', tags=['认证'])

def find_user(db: Session, username: str) -> Optional[User]:
    return db.scalar(select(User).where(User.username == username))

def find_phone_user(db: Session, phone: str) -> Optional[User]:
    return db.scalar(select(User).where(User.phone == phone))

def token_response(user: User, db: Session, is_new: bool = False,
                   accepted_terms_version: Optional[str] = None) -> TokenResponse:
    token = create_access_token(user.id, user.username)
    claims = decode_access_token(token)
    db.add(UserSession(user_id=user.id, token_hash=token_fingerprint(token),
                       expires_at=datetime.utcfromtimestamp(int(claims['exp'])),
                       accepted_terms_version=accepted_terms_version,
                       terms_accepted_at=datetime.utcnow() if accepted_terms_version else None))
    db.commit()
    return TokenResponse(access_token=token, user=UserOut.model_validate(user), is_new=is_new)


def latest_verified_sms(db: Session, phone: str, scene: str) -> Optional[SmsVerificationRecord]:
    """Return the latest locally recorded successful SMS verification."""

    return db.scalar(
        select(SmsVerificationRecord)
        .where(
            SmsVerificationRecord.phone == phone,
            SmsVerificationRecord.scene == scene,
            SmsVerificationRecord.status == 'VERIFIED',
            SmsVerificationRecord.sent_at >= datetime.utcnow() - timedelta(seconds=300),
            SmsVerificationRecord.sent_at <= datetime.utcnow(),
            SmsVerificationRecord.verified_at >= datetime.utcnow() - timedelta(seconds=300),
        )
        .order_by(SmsVerificationRecord.verified_at.desc(), SmsVerificationRecord.id.desc())
    )


def consume_verified_sms(db: Session, record: Optional[SmsVerificationRecord]) -> None:
    if not record:
        raise HTTPException(status_code=400, detail='验证码错误或已过期')
    cutoff = datetime.utcnow() - timedelta(seconds=300)
    result = db.execute(
        update(SmsVerificationRecord)
        .where(
            SmsVerificationRecord.id == record.id,
            SmsVerificationRecord.status == 'VERIFIED',
            SmsVerificationRecord.sent_at >= cutoff,
            SmsVerificationRecord.sent_at <= datetime.utcnow(),
            SmsVerificationRecord.verified_at >= cutoff,
        )
        .values(status='CONSUMED')
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail='验证码错误或已过期')

@router.post('/register', response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if find_user(db, payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该登录名已注册')
    if find_phone_user(db, payload.phone):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该手机号已绑定其他账号')
    verified_record: Optional[SmsVerificationRecord] = None
    if payload.registration_token:
        try:
            claims = decode_registration_token(payload.registration_token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if claims.get('phone') != payload.phone:
            raise HTTPException(status_code=400, detail='注册凭证与手机号不匹配')
        try:
            verification_id = int(claims['verification_id'])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail='注册凭证无效或已过期') from exc
        verified_record = db.scalar(
            select(SmsVerificationRecord)
            .where(
                SmsVerificationRecord.id == verification_id,
                SmsVerificationRecord.phone == payload.phone,
                SmsVerificationRecord.scene == 'login',
                SmsVerificationRecord.status == 'VERIFIED',
                SmsVerificationRecord.sent_at >= datetime.utcnow() - timedelta(seconds=300),
                SmsVerificationRecord.sent_at <= datetime.utcnow(),
                SmsVerificationRecord.verified_at >= datetime.utcnow() - timedelta(seconds=300),
            )
        )
        if not verified_record:
            raise HTTPException(status_code=400, detail='注册凭证无效或已使用')
    else:
        if not payload.sms_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='请填写短信验证码')
        try:
            verified = bool(check_sms_code(db, payload.phone, payload.sms_code, 'register'))
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='验证码错误或已过期')
        verified_record = latest_verified_sms(db, payload.phone, 'register')
    if not verified_record:
        raise HTTPException(status_code=400, detail='请先验证手机号')
    user = User(username=payload.username, phone=payload.phone, password_hash=hash_password(payload.password))
    try:
        consume_verified_sms(db, verified_record)
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback(); raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该登录名或手机号已注册')
    return token_response(user, db, is_new=True, accepted_terms_version=payload.accepted_terms_version)

@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not payload.has_one_identifier:
        raise HTTPException(status_code=422, detail='请填写登录名或手机号其中一项')
    user = find_user(db, payload.username) if payload.username else find_phone_user(db, payload.phone)
    if not user or not verify_password(payload.password, user.password_hash):
        db.add(LoginLog(identifier=payload.username or payload.phone or '', user_id=user.id if user else None, success=False)); db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='登录名、手机号或密码错误')
    db.add(LoginLog(identifier=payload.username or payload.phone or '', user_id=user.id, success=True)); db.commit()
    return token_response(user, db, accepted_terms_version=payload.accepted_terms_version)


@router.post('/login/sms', response_model=SmsLoginResponse)
@router.post('/sms-login', response_model=SmsLoginResponse, include_in_schema=False)
def sms_login(payload: SmsLoginRequest, db: Session = Depends(get_db)) -> SmsLoginResponse:
    """Log in with a phone SMS, or return the registration hand-off for a new phone."""

    try:
        verified = bool(check_sms_code(db, payload.phone, payload.sms_code, 'login'))
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not verified:
        db.add(LoginLog(identifier=payload.phone, user_id=None, success=False))
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='验证码错误或已过期')

    user = find_phone_user(db, payload.phone)
    if user:
        consume_verified_sms(db, latest_verified_sms(db, payload.phone, 'login'))
        db.add(LoginLog(identifier=payload.phone, user_id=user.id, success=True))
        db.commit()
        token = token_response(user, db, accepted_terms_version=payload.accepted_terms_version)
        return SmsLoginResponse(
            access_token=token.access_token,
            token_type=token.token_type,
            user=token.user,
            is_new=False,
            requires_registration=False,
            phone=payload.phone,
        )

    record = latest_verified_sms(db, payload.phone, 'login')
    if not record:
        raise HTTPException(status_code=500, detail='手机号验证记录异常，请重新获取验证码')
    registration_token = create_registration_token(payload.phone, record.id)
    db.add(LoginLog(identifier=payload.phone, user_id=None, success=True))
    db.commit()
    return SmsLoginResponse(
        is_new=True,
        requires_registration=True,
        phone=payload.phone,
        registration_token=registration_token,
    )

@router.post('/send-sms')
def send_sms_code(payload: SendSmsRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return send_sms(db, payload.phone, payload.scene)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post('/forgot-password')
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    user = find_phone_user(db, payload.phone)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='该手机号尚未注册')
    try:
        verified = bool(check_sms_code(db, payload.phone, payload.sms_code, 'reset_password'))
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not verified:
        raise HTTPException(status_code=400, detail='验证码错误或已过期')
    consume_verified_sms(db, latest_verified_sms(db, payload.phone, 'reset_password'))
    user.password_hash = hash_password(payload.new_password)
    user.sessions_valid_after = datetime.utcnow()
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=datetime.utcnow()))
    revoke_device_subscriptions(db, user.id)
    audit(db, user, 'password_reset')
    db.commit()
    return {'message': '密码已重置，请使用新密码登录'}

@router.get('/me', response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post('/bind-phone', response_model=UserOut)
def bind_phone(payload: BindPhoneRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if payload.scene == 'verify_phone':
        raise HTTPException(status_code=400, detail='绑定或更换手机号请使用对应验证码场景')
    phone_owner = find_phone_user(db, payload.phone)
    if phone_owner and phone_owner.id != user.id:
        raise HTTPException(status_code=409, detail='该手机号已绑定其他账号')
    try:
        verified = check_sms_code(db, payload.phone, payload.sms_code, payload.scene)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not verified:
        raise HTTPException(status_code=400, detail='验证码错误或已过期')
    consume_verified_sms(db, latest_verified_sms(db, payload.phone, payload.scene))
    previous_phone = user.phone
    user.phone = payload.phone
    if previous_phone and previous_phone != payload.phone:
        db.execute(delete(SmsVerificationRecord).where(SmsVerificationRecord.phone == previous_phone))
    audit(db, user, 'phone_bound')
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail='该手机号已绑定其他账号') from exc
    db.refresh(user)
    return user


@router.post('/logout')
def logout(user: User = Depends(get_current_user), credentials=Depends(bearer), db: Session = Depends(get_db)):
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_fingerprint(credentials.credentials)))
    session.revoked_at = datetime.utcnow()
    revoke_device_subscriptions(db, user.id, session.id)
    audit(db, user, 'session_logout', 'session', str(session.id))
    db.commit()
    return {'message': '已退出登录，当前会话已撤销'}


@router.get('/sessions')
def sessions(user: User = Depends(get_current_user), credentials=Depends(bearer), db: Session = Depends(get_db)):
    fingerprint = token_fingerprint(credentials.credentials)
    records = db.scalars(select(UserSession).where(UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None), UserSession.expires_at > datetime.utcnow())
        .order_by(UserSession.created_at.desc(), UserSession.id.desc()))
    return [{'id': record.id, 'created_at': record.created_at.isoformat() + 'Z',
             'expires_at': record.expires_at.isoformat() + 'Z', 'current': record.token_hash == fingerprint}
            for record in records]


@router.delete('/sessions/{session_id}')
def revoke_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(UserSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail='登录会话不存在')
    session.revoked_at = datetime.utcnow()
    revoke_device_subscriptions(db, user.id, session.id)
    audit(db, user, 'session_revoked', 'session', str(session.id))
    db.commit()
    return {'message': '已撤销该登录会话'}


@router.patch('/preferences', response_model=UserOut)
def preferences(payload: PreferencesRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    values = payload.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise HTTPException(status_code=422, detail='请提供需要修改的通知设置')
    for key, value in values.items():
        setattr(user, key, value)
    user.privacy_updated_at = datetime.utcnow()
    audit(db, user, 'preferences_updated')
    db.commit()
    db.refresh(user)
    return user


@router.delete('/me')
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset_ids = delete_user_data(db, user)
    from app.services.assets import delete_asset_files
    delete_asset_files(asset_ids)
    return {'message': '账号及其拥有的家谱资料已注销，其他家族的成员资格已移除'}
