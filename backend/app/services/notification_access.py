"""投递前读取当前家族权限，避免撤销协作者后继续发送旧消息。"""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Family, FamilyMembership, NotificationRecord, Reminder


def can_receive_family_notification(db: Session, notice: NotificationRecord) -> bool:
    """个人通知可投递；家族通知要求家族仍存在且收件人仍有权限。

    只查询、不提交事务，也不依赖用户当前选中的家族或 ORM 缓存。
    三个推送通道应在调用供应商前使用这一校验。
    """
    # 直接查询列以绕过其他 worker 修改前的 ORM 缓存。
    fingerprint = db.scalar(select(NotificationRecord.source_fingerprint).where(NotificationRecord.id == notice.id))
    if fingerprint in {'cancelled', 'catchup'}:
        return False
    if fingerprint:
        from app.services.notifications import reminder_fingerprint
        reminder = db.scalar(select(Reminder).where(Reminder.id == notice.reminder_id).execution_options(populate_existing=True))
        if not reminder or reminder_fingerprint(reminder) != fingerprint:
            return False
    if notice.family_id is None:
        return True
    membership = select(FamilyMembership.id).where(
        FamilyMembership.family_id == notice.family_id,
        FamilyMembership.user_id == notice.user_id,
    ).exists()
    family_id = db.scalar(select(Family.id).where(
        Family.id == notice.family_id,
        or_(Family.owner_id == notice.user_id, membership),
    ))
    return family_id is not None
