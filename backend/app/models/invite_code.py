"""真实家族邀请码及跨 worker 的持久化限流记录。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class FamilyInviteCode(Base):
    __tablename__ = 'family_invite_codes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False)
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    inviter_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='PENDING', nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class InviteCodeRateLimit(Base):
    __tablename__ = 'invite_code_rate_limits'

    key: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
