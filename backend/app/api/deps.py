from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, token_fingerprint
from app.db.session import get_db
from app.models.user import User, UserSession


bearer = HTTPBearer(auto_error=False)


def authenticate_token(token: str, db: Session) -> User:
    """验证签名和数据库会话；旧版本 JWT 仅首次登记，撤销后不能复活。"""
    payload = decode_access_token(token)
    user = db.get(User, int(payload['sub']))
    if not user or payload.get('username') != user.username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='用户不存在，请重新登录')
    valid_after = getattr(user, 'sessions_valid_after', None)
    if valid_after:
        cutoff = int(valid_after.replace(tzinfo=timezone.utc).timestamp())
        issued_at = int(payload.get('iat', 0))
        # 旧 JWT 没有已登记的签发会话，同秒签发也必须视为撤销前的令牌。
        # 新 JWT 仍按会话撤销状态判断，允许同秒重置密码后重新登录。
        if issued_at < cutoff or (not payload.get('jti') and issued_at == cutoff):
            raise HTTPException(status_code=401, detail='密码已变更，请重新登录')
    fingerprint = token_fingerprint(token)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == fingerprint))
    if not session:
        # 本版本的令牌在签发时已登记。只有旧版、不含 jti 的 JWT 可以迁移。
        if payload.get('jti'):
            raise HTTPException(status_code=401, detail='登录会话不存在，请重新登录')
        session = UserSession(user_id=user.id, token_hash=fingerprint,
                              expires_at=datetime.utcfromtimestamp(int(payload['exp'])))
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            session = db.scalar(select(UserSession).where(UserSession.token_hash == fingerprint))
    if not session or session.user_id != user.id or session.revoked_at or session.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=401, detail='登录会话已撤销或过期，请重新登录')
    return user


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='请先登录')
    return authenticate_token(credentials.credentials, db)
