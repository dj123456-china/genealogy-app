from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base

class WechatDevice(Base):
    __tablename__ = 'wechat_devices'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    session_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    open_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    allowance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

class WechatDelivery(Base):
    __tablename__ = 'wechat_deliveries'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='PENDING', nullable=False)
    attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
