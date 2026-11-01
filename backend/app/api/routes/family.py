from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import (AuditLog, Family, FamilyMember, FamilyMembership, FamilyRelationship,
                        Invitation, NotificationRecord, Reminder, User, WechatDelivery)
from app.schemas.family import (ActiveFamilyPayload, AuditOut, FamilyProfile, FamilySummary,
                                InviteOut, InvitePayload, MemberOut, MemberPayload, MembershipOut,
                                MembershipPayload, ReminderOut, ReminderPayload, SyncData, SyncOut)
from app.services.family import (active_members, audit, family_for, member_out, new_client_id,
                                 role_for, save_snapshot, snapshot, snapshot_payload)
from app.models import FamilyVersion, FamilyInviteCode, FileAsset
from app.schemas.family import TransferPayload, RestorePayload
from app.services.family import _validate_graph, graph_warnings, reserve_revision
import json

router = APIRouter(prefix='/family', tags=['家族资料'])


@router.get('/sync', response_model=SyncOut)
def get_sync(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    return snapshot(db, family_for(db, user, family_id), user)


@router.put('/sync', response_model=SyncOut)
def put_sync(payload: SyncData, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return save_snapshot(db, user, payload)


@router.get('/list', response_model=list[FamilySummary])
def list_families(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    active = family_for(db, user)
    member_family_ids = select(FamilyMembership.family_id).where(FamilyMembership.user_id == user.id)
    rows = db.scalars(select(Family).where(or_(Family.owner_id == user.id, Family.id.in_(member_family_ids))).order_by(Family.id)).all()
    return [FamilySummary(id=family.id, owner_id=family.owner_id, name=family.name, avatar=family.avatar, revision=family.revision,
                          role=role_for(db, family, user), active=family.id == active.id,
                          personal=family.personal_owner_id == user.id) for family in rows]


@router.put('/active', response_model=SyncOut)
def select_active_family(payload: ActiveFamilyPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, payload.family_id)
    user.active_family_id = family.id
    audit(db, user, family, 'family.select')
    db.commit()
    return snapshot(db, family, user)


@router.get('/profile', response_model=FamilyProfile)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    return get_sync(user, db, family_id).profile


@router.put('/profile', response_model=SyncOut)
def put_profile(payload: FamilyProfile, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    data.profile = payload
    return save_snapshot(db, user, data, 'family.profile')


@router.get('/members', response_model=list[MemberOut])
def list_members(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    return get_sync(user, db, family_id).members


@router.get('/relationships')
def list_relationships(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id)
    rows = db.scalars(select(FamilyRelationship).where(FamilyRelationship.family_id == family.id).order_by(FamilyRelationship.id)).all()
    return [{'id': row.id, 'from_member_id': row.from_member_id, 'to_member_id': row.to_member_id, 'kind': row.kind} for row in rows]


@router.get('/tree', response_model=list[MemberOut])
def family_tree(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    return list_members(user, db, family_id)


@router.post('/members', response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(payload: MemberPayload, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    payload = payload.model_copy(update={'client_id': payload.client_id or new_client_id('member')})
    if any(member.client_id == payload.client_id for member in data.members):
        raise HTTPException(status_code=409, detail='该成员 client_id 已存在')
    data.members.append(payload)
    result = save_snapshot(db, user, data, 'member.add')
    return next(member for member in result.members if member.client_id == payload.client_id)


@router.put('/members/{member_id}', response_model=MemberOut)
def update_member(member_id: int, payload: MemberPayload, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    current = next((member for member in data.members if getattr(member, 'id', None) == member_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail='成员不存在')
    if payload.client_id and payload.client_id != current.client_id:
        raise HTTPException(status_code=422, detail='成员 client_id 不能变更')
    payload = payload.model_copy(update={'client_id': current.client_id})
    # 显式改配偶时，释放旧配偶的反向关系，再由全图验证补齐新的关系。
    if current.spouse_client_id and current.spouse_client_id != payload.spouse_client_id:
        for other in data.members:
            if other.client_id == current.spouse_client_id and other.spouse_client_id == current.client_id:
                other.spouse_id, other.spouse_client_id = None, None
    data.members = [payload if member.client_id == current.client_id else member for member in data.members]
    result = save_snapshot(db, user, data, 'member.edit')
    return next(member for member in result.members if member.id == member_id)


@router.delete('/members/{member_id}')
def delete_member(member_id: int, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    current = next((member for member in data.members if getattr(member, 'id', None) == member_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail='成员不存在')
    data.members = [member for member in data.members if member.client_id != current.client_id]
    for member in data.members:
        member.history_links = [link for link in member.history_links if link.member_client_id != current.client_id]
        if member.parent_roles:
            member.parent_roles = [role for parent, role in zip(member.parent_client_ids, member.parent_roles)
                                   if parent != current.client_id]
        member.parent_ids = [parent for parent in member.parent_ids if parent != member_id]
        member.parent_client_ids = [parent for parent in member.parent_client_ids if parent != current.client_id]
        if member.spouse_id == member_id or member.spouse_client_id == current.client_id:
            member.spouse_id, member.spouse_client_id = None, None
    # 保留独立纪念日，解除被删除人员的关联。
    for reminder in data.reminders:
        if reminder.member_id == member_id or reminder.member_client_id == current.client_id:
            reminder.member_id, reminder.member_client_id = None, None
    result = save_snapshot(db, user, data, 'member.remove')
    return {'message': '成员已删除', 'family_id': family.id, 'revision': result.revision}


@router.get('/reminders', response_model=list[ReminderOut])
def list_reminders(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    return get_sync(user, db, family_id).reminders


@router.post('/reminders', response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(payload: ReminderPayload, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    payload = payload.model_copy(update={'client_id': payload.client_id or new_client_id('reminder')})
    if any(reminder.client_id == payload.client_id for reminder in data.reminders):
        raise HTTPException(status_code=409, detail='该纪念日 client_id 已存在')
    data.reminders.append(payload)
    result = save_snapshot(db, user, data, 'reminder.add')
    return next(reminder for reminder in result.reminders if reminder.client_id == payload.client_id)


@router.put('/reminders/{reminder_id}', response_model=ReminderOut)
def update_reminder(reminder_id: int, payload: ReminderPayload, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    current = next((reminder for reminder in data.reminders if getattr(reminder, 'id', None) == reminder_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail='提醒不存在')
    if payload.client_id and payload.client_id != current.client_id:
        raise HTTPException(status_code=422, detail='纪念日 client_id 不能变更')
    payload = payload.model_copy(update={'client_id': current.client_id})
    data.reminders = [payload if reminder.client_id == current.client_id else reminder for reminder in data.reminders]
    result = save_snapshot(db, user, data, 'reminder.edit')
    return next(reminder for reminder in result.reminders if reminder.id == reminder_id)


@router.delete('/reminders/{reminder_id}')
def delete_reminder(reminder_id: int, family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, write=True)
    data = snapshot_payload(db, user, family, revision)
    if not any(getattr(reminder, 'id', None) == reminder_id for reminder in data.reminders):
        raise HTTPException(status_code=404, detail='提醒不存在')
    data.reminders = [reminder for reminder in data.reminders if getattr(reminder, 'id', None) != reminder_id]
    result = save_snapshot(db, user, data, 'reminder.remove')
    return {'message': '提醒已删除', 'family_id': family.id, 'revision': result.revision}


@router.delete('/data', response_model=SyncOut)
def clear_data(family_id: int = Query(..., gt=0), revision: int = Query(..., ge=0),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, owner=True)
    return save_snapshot(db, user, SyncData(family_id=family.id, revision=revision), 'family.clear')


@router.get('/export', response_model=SyncOut)
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    return get_sync(user, db, family_id)


@router.post('/import', response_model=SyncOut)
def import_data(payload: SyncData, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return save_snapshot(db, user, payload, 'family.import')


@router.post('/validate')
def validate_import(payload: SyncData, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, payload.family_id, owner=True)
    graph, _ = _validate_graph(payload, active_members(db, family.id), [])
    return {'valid': True, 'warnings': graph_warnings(list(graph.values()))}


@router.get('/versions')
def list_versions(family_id: int = Query(..., gt=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family_for(db, user, family_id, owner=True)
    rows = db.scalars(select(FamilyVersion).where(FamilyVersion.family_id == family_id).order_by(FamilyVersion.id.desc()).limit(100))
    return [{'id': row.id, 'revision': row.revision, 'action': row.action, 'user_id': row.user_id,
             'created_at': row.created_at.isoformat() + 'Z'} for row in rows]


@router.post('/versions/{version_id}/restore', response_model=SyncOut)
def restore_version(version_id: int, payload: RestorePayload, family_id: int = Query(..., gt=0),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family_for(db, user, family_id, owner=True)
    version = db.get(FamilyVersion, version_id)
    if not version or version.family_id != family_id:
        raise HTTPException(status_code=404, detail='家谱版本不存在')
    data = json.loads(version.data)
    data.update(family_id=family_id, revision=payload.revision)
    return save_snapshot(db, user, SyncData.model_validate(data), 'family.restore')


@router.get('/trash')
def list_trash(family_id: int = Query(..., gt=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family_for(db, user, family_id, owner=True)
    rows = db.scalars(select(FamilyMember).where(FamilyMember.family_id == family_id,
        FamilyMember.deleted_at.is_not(None)).order_by(FamilyMember.deleted_at.desc()).limit(200))
    return [{'client_id': row.client_id, 'name': row.name, 'deleted_at': row.deleted_at.isoformat() + 'Z'} for row in rows]


@router.post('/trash/{client_id}/restore', response_model=SyncOut)
def restore_member(client_id: str, payload: RestorePayload, family_id: int = Query(..., gt=0),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, owner=True)
    row = db.scalar(select(FamilyMember).where(FamilyMember.family_id == family_id,
        FamilyMember.client_id == client_id, FamilyMember.deleted_at.is_not(None)))
    if not row:
        raise HTTPException(status_code=404, detail='回收站成员不存在')
    data = snapshot_payload(db, user, family, payload.revision)
    recovered = member_out(row)
    # 单人恢复保留档案，原世系和纪念日由整谱版本恢复，避免引用已不存在的成员。
    recovered.parent_ids, recovered.parent_client_ids, recovered.parent_roles = [], [], []
    recovered.spouse_id, recovered.spouse_client_id, recovered.history_links = None, None, []
    if recovered.relation == '本人' and any(m.relation == '本人' for m in data.members):
        recovered.relation = '其他亲属'
    data.members.append(recovered)
    return save_snapshot(db, user, data, 'member.restore')


@router.post('/transfer', response_model=SyncOut)
def transfer_family(payload: TransferPayload, family_id: int = Query(..., gt=0),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id, owner=True)
    target = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family_id,
        FamilyMembership.user_id == payload.user_id).with_for_update())
    if not target or payload.user_id == user.id:
        raise HTTPException(status_code=422, detail='请选择另一位现有协作者接管家谱')
    reserve_revision(db, family, user, payload.revision)
    previous = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family_id, FamilyMembership.user_id == user.id))
    if not previous:
        previous = FamilyMembership(family_id=family_id, user_id=user.id, role='EDITOR')
        db.add(previous)
    previous.role, target.role = 'EDITOR', 'OWNER'
    family.owner_id, family.personal_owner_id = payload.user_id, None
    # 管理员移交包含家族资产，原所有者注销后仍能读取头像。
    for asset in db.scalars(select(FileAsset).where(FileAsset.family_id == family_id)):
        asset.owner_id = payload.user_id
    for code in db.scalars(select(FamilyInviteCode).where(FamilyInviteCode.family_id == family_id, FamilyInviteCode.status == 'PENDING')):
        code.status = 'CANCELLED'
    for invitation in db.scalars(select(Invitation).where(Invitation.family_id == family_id, Invitation.status == 'PENDING')):
        invitation.status = 'CANCELLED'
    audit(db, user, family, 'family.transfer', changes=json.dumps({'from': user.id, 'to': payload.user_id}))
    db.commit()
    return snapshot(db, family, user)


@router.post('/leave')
def leave_family(family_id: int = Query(..., gt=0), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    family = family_for(db, user, family_id)
    # 与所有写和移交同一 family 锁，退出不能与权限操作穿插。
    db.scalar(select(Family).where(Family.id == family.id).with_for_update())
    if family.owner_id == user.id:
        raise HTTPException(status_code=422, detail='管理员须先移交家谱，才能退出')
    row = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family_id, FamilyMembership.user_id == user.id))
    notices = select(NotificationRecord.id).where(NotificationRecord.family_id == family_id, NotificationRecord.user_id == user.id)
    db.execute(delete(WechatDelivery).where(WechatDelivery.notification_id.in_(notices)))
    db.execute(delete(NotificationRecord).where(NotificationRecord.family_id == family_id, NotificationRecord.user_id == user.id))
    db.delete(row)
    if user.active_family_id == family_id:
        user.active_family_id = None
    audit(db, user, family, 'membership.leave')
    db.commit()
    return {'message': '已退出家谱，个人家谱保留'}


def invite_out(db: Session, invitation: Invitation) -> InviteOut:
    family = db.get(Family, invitation.family_id)
    inviter = db.get(User, invitation.inviter_id)
    if invitation.status == 'PENDING' and invitation.expires_at and invitation.expires_at <= datetime.utcnow():
        invitation.status = 'EXPIRED'
    return InviteOut(id=invitation.id, family_id=invitation.family_id,
                     family_name=family.name if family else '已删除家族',
                     inviter=inviter.username if inviter else '已注销用户', invitee=invitation.invitee,
                     role=invitation.role, status=invitation.status, expires_at=invitation.expires_at)


@router.post('/invitations', response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invitation(payload: InvitePayload, user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id, owner=True)
    invitee = db.scalar(select(User).where(or_(User.username == payload.invitee, User.phone == payload.invitee)))
    if not invitee:
        raise HTTPException(status_code=404, detail='请邀请已经注册的登录名或手机号')
    if invitee.id == user.id:
        raise HTTPException(status_code=422, detail='不能邀请自己')
    if db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family.id, FamilyMembership.user_id == invitee.id)):
        raise HTTPException(status_code=409, detail='该用户已加入家族')
    pending = db.scalar(select(Invitation).where(Invitation.family_id == family.id, Invitation.invitee_user_id == invitee.id, Invitation.status == 'PENDING', Invitation.expires_at > datetime.utcnow()))
    if pending:
        raise HTTPException(status_code=409, detail='该用户已有待处理邀请')
    record = Invitation(family_id=family.id, inviter_id=user.id, invitee=invitee.username,
                        invitee_user_id=invitee.id, role=payload.role, status='PENDING',
                        expires_at=datetime.utcnow() + timedelta(days=14))
    db.add(record)
    db.flush()
    audit(db, user, family, 'invitation.create', 'invitation', record.id)
    db.commit()
    return invite_out(db, record)


@router.get('/invitations', response_model=list[InviteOut])
def list_invitations(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id, owner=True)
    rows = db.scalars(select(Invitation).where(Invitation.family_id == family.id).order_by(Invitation.id.desc())).all()
    result = [invite_out(db, invitation) for invitation in rows]
    db.commit()
    return result


@router.get('/invitations/incoming', response_model=list[InviteOut])
def incoming_invitations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 旧邀请只在其没有固化收件人的情况下按现有用户标识兼容。
    identifiers = [user.username] + ([user.phone] if user.phone else [])
    rows = db.scalars(select(Invitation).where(
        Invitation.status == 'PENDING',
        or_(Invitation.invitee_user_id == user.id,
            (Invitation.invitee_user_id.is_(None) & Invitation.invitee.in_(identifiers)))
    ).order_by(Invitation.id.desc())).all()
    result = [invite_out(db, invitation) for invitation in rows]
    db.commit()
    return result


def pending_invitation(db: Session, invitation_id: int, user: User) -> Invitation:
    row = db.scalar(select(Invitation).where(Invitation.id == invitation_id).with_for_update())
    if not row:
        raise HTTPException(status_code=404, detail='邀请不存在')
    allowed = row.invitee_user_id == user.id if row.invitee_user_id is not None else row.invitee in {user.username, user.phone}
    if not allowed:
        raise HTTPException(status_code=403, detail='该邀请不属于当前账号')
    if row.status != 'PENDING':
        raise HTTPException(status_code=409, detail='邀请已处理')
    if row.expires_at and row.expires_at <= datetime.utcnow():
        row.status = 'EXPIRED'
        db.commit()
        raise HTTPException(status_code=410, detail='邀请已过期，请家族所有者重新邀请')
    return row


@router.post('/invitations/{invitation_id}/accept', response_model=SyncOut)
def accept_invitation(invitation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = pending_invitation(db, invitation_id, user)
    family = db.get(Family, row.family_id)
    if not family:
        raise HTTPException(status_code=404, detail='家族不存在')
    membership = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id))
    if not membership:
        db.add(FamilyMembership(family_id=family.id, user_id=user.id, role=row.role))
    row.status = 'ACCEPTED'
    row.invitee_user_id = user.id
    user.active_family_id = family.id
    audit(db, user, family, 'invitation.accept', 'invitation', row.id)
    db.commit()
    return snapshot(db, family, user)


@router.post('/invitations/{invitation_id}/reject', response_model=InviteOut)
def reject_invitation(invitation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = pending_invitation(db, invitation_id, user)
    row.status = 'REJECTED'
    family = db.get(Family, row.family_id)
    if family:
        audit(db, user, family, 'invitation.reject', 'invitation', row.id)
    db.commit()
    return invite_out(db, row)


@router.post('/invitations/{invitation_id}/cancel', response_model=InviteOut)
@router.delete('/invitations/{invitation_id}', response_model=InviteOut)
def cancel_invitation(invitation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Invitation, invitation_id)
    if not row:
        raise HTTPException(status_code=404, detail='邀请不存在')
    family = family_for(db, user, row.family_id, owner=True)
    if row.status != 'PENDING':
        raise HTTPException(status_code=409, detail='邀请已处理')
    row.status = 'CANCELLED'
    audit(db, user, family, 'invitation.cancel', 'invitation', row.id)
    db.commit()
    return invite_out(db, row)


@router.get('/memberships', response_model=list[MembershipOut])
def list_memberships(user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id)
    rows = db.scalars(select(FamilyMembership).where(FamilyMembership.family_id == family.id).order_by(FamilyMembership.id)).all()
    result = []
    for row in rows:
        member_user = db.get(User, row.user_id)
        if member_user:
            result.append(MembershipOut(id=row.id, user_id=row.user_id, username=member_user.username,
                                       role='OWNER' if row.user_id == family.owner_id else ('VIEWER' if row.role == 'VIEWER' else 'EDITOR')))
    return result


@router.put('/memberships/{membership_id}', response_model=MembershipOut)
@router.patch('/memberships/{membership_id}', response_model=MembershipOut)
def update_membership(membership_id: int, payload: MembershipPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id, owner=True)
    row = db.scalar(select(FamilyMembership).where(FamilyMembership.id == membership_id, FamilyMembership.family_id == family.id))
    if not row:
        raise HTTPException(status_code=404, detail='家族成员不存在')
    if row.user_id == family.owner_id:
        raise HTTPException(status_code=422, detail='不能改变家族所有者的权限')
    row.role = payload.role
    audit(db, user, family, 'membership.role', 'membership', row.id)
    db.commit()
    member_user = db.get(User, row.user_id)
    return MembershipOut(id=row.id, user_id=row.user_id, username=member_user.username, role=row.role)


@router.delete('/memberships/{membership_id}')
def delete_membership(membership_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id, owner=True)
    row = db.scalar(select(FamilyMembership).where(FamilyMembership.id == membership_id, FamilyMembership.family_id == family.id))
    if not row:
        raise HTTPException(status_code=404, detail='家族成员不存在')
    if row.user_id == family.owner_id:
        raise HTTPException(status_code=422, detail='不能移除家族所有者')
    removed_user = db.get(User, row.user_id)
    if removed_user and removed_user.active_family_id == family.id:
        removed_user.active_family_id = None
    notices = select(NotificationRecord.id).where(
        NotificationRecord.user_id == row.user_id,
        NotificationRecord.family_id == family.id,
    )
    # 与成员资格撤销同一事务清理，保留其他家族、个人和其他用户的通知。
    db.execute(delete(WechatDelivery).where(WechatDelivery.notification_id.in_(notices)))
    db.execute(delete(NotificationRecord).where(
        NotificationRecord.user_id == row.user_id,
        NotificationRecord.family_id == family.id,
    ))
    audit(db, user, family, 'membership.remove', 'membership', row.id)
    db.delete(row)
    db.commit()
    return {'message': '家族成员已移除'}


@router.get('/audit', response_model=list[AuditOut])
def list_audit(limit: int = Query(default=100, ge=1, le=500), user: User = Depends(get_current_user), db: Session = Depends(get_db), family_id: Optional[int] = Query(default=None, gt=0)):
    family = family_for(db, user, family_id)
    rows = db.scalars(select(AuditLog).where(AuditLog.family_id == family.id).order_by(AuditLog.id.desc()).limit(limit)).all()
    result = []
    for row in rows:
        operator = db.get(User, row.user_id) if row.user_id else None
        result.append(AuditOut(id=row.id, user_id=row.user_id, username=operator.username if operator else '已注销用户',
                               action=row.action, target_type=row.target_type, target_id=row.target_id, created_at=row.created_at,
                               changes=row.changes or ''))
    return result
