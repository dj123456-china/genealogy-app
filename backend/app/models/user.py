from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, synonym
from app.db.session import Base

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(11), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active_family_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='1')
    system_notifications_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
    privacy_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sessions_valid_after: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Family(Base):
    __tablename__ = 'families'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    personal_owner_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default='我的家谱')
    avatar: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False, default='')
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class FamilyMember(Base):
    __tablename__ = 'family_members'
    __table_args__ = (UniqueConstraint('family_id', 'client_id', name='uq_member_family_client'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False, default='其他亲属')
    gender: Mapped[str] = mapped_column(String(8), nullable=False, default='未知')
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    birthday: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    birth_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    birth_approximate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    history_links: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    relationship_note: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    death_year: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    death_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    deceased: Mapped[bool] = mapped_column(nullable=False, default=False)
    avatar_label: Mapped[str] = mapped_column(String(8), nullable=False, default='')
    avatar_name: Mapped[str] = mapped_column(String(32), nullable=False, default='')
    bio: Mapped[str] = mapped_column(String(2000), nullable=False, default='')
    parent_ids: Mapped[str] = mapped_column(String(512), nullable=False, default='[]')
    parent_roles: Mapped[str] = mapped_column(Text, nullable=False, default='[]')
    spouse_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class FamilyRelationship(Base):
    __tablename__ = 'family_relationships'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    from_member_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    to_member_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Reminder(Base):
    __tablename__ = 'reminders'
    __table_args__ = (UniqueConstraint('family_id', 'client_id', name='uq_reminder_family_client'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    member_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default='生日')
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    advance: Mapped[str] = mapped_column(String(32), nullable=False, default='当天')
    repeat: Mapped[str] = mapped_column(String(16), nullable=False, default='每年')
    calendar: Mapped[str] = mapped_column(String(16), nullable=False, default='solar', server_default='solar')
    lunar_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lunar_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lunar_leap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='0')
    calendar_type = synonym('calendar')
    is_leap = synonym('lunar_leap')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class SmsVerificationRecord(Base):
    __tablename__ = 'sms_verification_records'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone: Mapped[str] = mapped_column(String(11), index=True, nullable=False)
    scene: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='SENT')


class LoginLog(Base):
    __tablename__ = 'login_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(nullable=False, default=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Invitation(Base):
    __tablename__ = 'invitations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    inviter_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invitee: Mapped[str] = mapped_column(String(64), nullable=False)
    invitee_user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default='EDITOR', server_default='EDITOR')
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FamilyMembership(Base):
    __tablename__ = 'family_memberships'
    __table_args__ = (UniqueConstraint('family_id', 'user_id', name='uq_membership_family_user'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default='EDITOR')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FileAsset(Base):
    __tablename__ = 'file_assets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, default='', server_default='')
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default='', server_default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default='')
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    changes: Mapped[str] = mapped_column(Text, nullable=False, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class UserSession(Base):
    __tablename__ = 'user_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_terms_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class NotificationRecord(Base):
    __tablename__ = 'notification_records'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    reminder_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, default='', server_default='')
    body: Mapped[str] = mapped_column(Text, nullable=False, default='')
    due_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivery_error: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    push_status: Mapped[str] = mapped_column(String(32), nullable=False, default='DISABLED', server_default='DISABLED')
    push_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    push_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mobile_status: Mapped[str] = mapped_column(String(32), nullable=False, default='DISABLED', server_default='DISABLED')
    mobile_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    mobile_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING')
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False)
    endpoint_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200), nullable=False)
    auth: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class MobilePushDevice(Base):
    __tablename__ = 'mobile_push_devices'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    client_id: Mapped[str] = mapped_column(String(256), nullable=False)
    client_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FamilyVersion(Base):
    __tablename__ = 'family_versions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    family_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SchedulerCheckpoint(Base):
    __tablename__ = 'scheduler_checkpoints'
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_on: Mapped[str] = mapped_column(String(10), nullable=False)
