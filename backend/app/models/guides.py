"""按账号保存导览偏好，不跟随家族切换。"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class UserGuideSetting(Base):
    __tablename__ = 'user_guide_settings'

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    permanently_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
    dismissed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
