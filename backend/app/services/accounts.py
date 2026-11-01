"""账户生命周期和关联数据清理；仅在显式注销时删除真实资料。"""
from __future__ import annotations
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models import (AuditLog, Family, FamilyMember, FamilyMembership,
                        FamilyRelationship, FileAsset, Invitation, LoginLog,
                        NotificationRecord, Reminder, SmsVerificationRecord,
                        User, UserSession)


def audit(db: Session, user: User, action: str, target_type: str = 'account', target_id: str = ''):
    db.add(AuditLog(user_id=user.id, family_id=getattr(user, 'active_family_id', None),
                    action=action, target_type=target_type, target_id=target_id or str(user.id)))


def delete_user_data(db: Session, user: User) -> list[int]:
    """清理其所有家族、其他家族成员资格、邀请、会话、通知、文件和手机号验证记录。"""
    # 与邀请码加入采用相同的 user -> family 锁顺序，避免注销期间产生孤立资格。
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    owned_ids = list(db.scalars(select(Family.id).where(Family.owner_id == user.id).order_by(Family.id).with_for_update()))
    from app.services.invite_codes import delete_invite_code_data
    delete_invite_code_data(db, user.id, owned_ids)
    from app.models.guides import UserGuideSetting
    db.execute(delete(UserGuideSetting).where(UserGuideSetting.user_id == user.id))
    from app.models.wechat import WechatDevice, WechatDelivery
    owned_notices = select(NotificationRecord.id).where(NotificationRecord.family_id.in_(owned_ids))
    db.execute(delete(WechatDelivery).where(or_(WechatDelivery.user_id == user.id, WechatDelivery.notification_id.in_(owned_notices))))
    db.execute(delete(WechatDevice).where(WechatDevice.user_id == user.id))
    asset_ids = list(db.scalars(select(FileAsset.id).where(
        or_(FileAsset.owner_id == user.id, FileAsset.family_id.in_(owned_ids)))))
    asset_urls = [f'/api/assets/{asset_id}/content' for asset_id in asset_ids]
    # 删除共享家族中引用其文件的头像，避免遗留失效图片；其余共享家谱保留。
    referenced_families = list(db.scalars(select(Family).where(
        Family.avatar.in_(asset_urls), Family.id.not_in(owned_ids)))) if asset_urls else []
    for family in referenced_families:
        family.avatar = ''
        family.revision += 1
        db.add(AuditLog(user_id=None, family_id=family.id, action='account_asset_removed',
                        target_type='family', target_id=str(family.id)))
    if owned_ids:
        db.execute(update(User).where(User.active_family_id.in_(owned_ids)).values(active_family_id=None))
    db.execute(delete(NotificationRecord).where(or_(NotificationRecord.user_id == user.id,
                                                    NotificationRecord.family_id.in_(owned_ids))))
    db.execute(delete(Invitation).where(or_(Invitation.family_id.in_(owned_ids),
                                           Invitation.inviter_id == user.id,
                                           Invitation.invitee_user_id == user.id,
                                           Invitation.invitee.in_([user.username, user.phone or '']))))
    db.execute(delete(FamilyMembership).where(or_(FamilyMembership.family_id.in_(owned_ids),
                                                 FamilyMembership.user_id == user.id)))
    db.execute(delete(FamilyRelationship).where(FamilyRelationship.family_id.in_(owned_ids)))
    db.execute(delete(Reminder).where(Reminder.family_id.in_(owned_ids)))
    db.execute(delete(FamilyMember).where(FamilyMember.family_id.in_(owned_ids)))
    db.execute(delete(FileAsset).where(FileAsset.id.in_(asset_ids)))
    db.execute(delete(AuditLog).where(AuditLog.family_id.in_(owned_ids)))
    db.execute(update(AuditLog).where(AuditLog.user_id == user.id).values(user_id=None))
    db.execute(delete(LoginLog).where(or_(LoginLog.user_id == user.id,
                                         LoginLog.identifier.in_([user.username, user.phone or '']))))
    if user.phone:
        db.execute(delete(SmsVerificationRecord).where(SmsVerificationRecord.phone == user.phone))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    # 可选 Web Push 订阅也属于个人资料。
    from app.models import user as models
    if hasattr(models, 'PushSubscription'):
        db.execute(delete(models.PushSubscription).where(models.PushSubscription.user_id == user.id))
    if hasattr(models, 'MobilePushDevice'):
        db.execute(delete(models.MobilePushDevice).where(models.MobilePushDevice.user_id == user.id))
    db.execute(delete(Family).where(Family.id.in_(owned_ids)))
    db.delete(user)
    db.commit()
    return asset_ids


def revoke_device_subscriptions(db: Session, user_id: int, session_id: int | None = None):
    from app.models.user import PushSubscription, MobilePushDevice
    from app.models.wechat import WechatDevice
    for model in (PushSubscription, MobilePushDevice, WechatDevice):
        criteria = [model.user_id == user_id]
        if session_id is not None:
            criteria.append(model.session_id == session_id)
        db.execute(delete(model).where(*criteria))
