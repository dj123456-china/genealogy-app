"""家族权限、整图校验与版本化持久化；所有写入口使用同一个事务规则。"""
import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditLog, Family, FamilyMember, FamilyMembership, FamilyRelationship, Reminder, User, FamilyVersion
from app.schemas.family import FamilyProfile, MemberOut, MemberPayload, ReminderOut, ReminderPayload, SyncData, SyncOut


def active_members(db: Session, family_id: int):
    return db.scalars(select(FamilyMember).where(FamilyMember.family_id == family_id, FamilyMember.deleted_at.is_(None)).order_by(FamilyMember.id)).all()


def role_for(db: Session, family: Family, user: User) -> str:
    if family.owner_id == user.id:
        return 'OWNER'
    membership = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id).execution_options(populate_existing=True))
    if not membership:
        raise HTTPException(status_code=403, detail='没有该家族的访问权限')
    return 'VIEWER' if membership.role == 'VIEWER' else 'EDITOR'


def family_for(db: Session, user: User, family_id: Optional[int] = None, write: bool = False, owner: bool = False) -> Family:
    selected_id = family_id or getattr(user, 'active_family_id', None)
    query = select(Family).where(Family.id == selected_id).execution_options(populate_existing=True)
    family = db.scalar(query.with_for_update() if write or owner else query) if selected_id else None
    if family_id and not family:
        raise HTTPException(status_code=404, detail='家族不存在')
    if family:
        try:
            role = role_for(db, family, user)
        except HTTPException:
            if family_id:
                raise
            family = None
    if family is None:
        family = db.scalar(select(Family).where(Family.owner_id == user.id, Family.personal_owner_id == user.id))
        if not family:
            try:
                with db.begin_nested():
                    family = Family(owner_id=user.id, personal_owner_id=user.id)
                    db.add(family)
                    db.flush()
            except IntegrityError:
                family = db.scalar(select(Family).where(Family.personal_owner_id == user.id))
                if not family:
                    raise
        role = 'OWNER'
        # 身份测试可使用 SimpleNamespace；真实用户的 active 家族必须落库。
        stored_user = db.get(User, user.id)
        if stored_user:
            stored_user.active_family_id = family.id
        owner_row = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id))
        if not owner_row:
            try:
                with db.begin_nested():
                    db.add(FamilyMembership(family_id=family.id, user_id=user.id, role='OWNER'))
                    db.flush()
            except IntegrityError:
                # 另一个启动请求已登记所有者成员资格。
                pass
        db.commit()
    if owner and role != 'OWNER':
        raise HTTPException(status_code=403, detail='只有家族所有者可以管理成员和邀请')
    if write and role not in {'OWNER', 'EDITOR'}:
        raise HTTPException(status_code=403, detail='当前为只读权限，不能修改家谱')
    return family


def member_out(member: FamilyMember, by_id=None) -> MemberOut:
    parents = json.loads(member.parent_ids or '[]')
    parent_roles = json.loads(member.parent_roles or '[]')
    by_id = by_id or {}
    return MemberOut(id=member.id, client_id=member.client_id or f'member-{member.id}', name=member.name,
                     relation=member.relation, gender=member.gender, generation=member.generation,
                     birthday=member.birthday, death_year=member.death_year, death_date=member.death_date, deceased=member.deceased,
                     birth_year=member.birth_year, birth_month=member.birth_month, birth_approximate=member.birth_approximate,
                     history_links=json.loads(member.history_links or '[]'), relationship_note=member.relationship_note or '',
                     avatar_label=member.avatar_label, avatar_name=member.avatar_name, bio=member.bio,
                     parent_ids=parents, parent_roles=parent_roles, spouse_id=member.spouse_id,
                     parent_client_ids=[by_id[x].client_id or f'member-{x}' for x in parents if x in by_id],
                     spouse_client_id=(by_id[member.spouse_id].client_id or f'member-{member.spouse_id}') if member.spouse_id in by_id else None)


def reminder_out(reminder: Reminder, by_id=None) -> ReminderOut:
    by_id = by_id or {}
    member = by_id.get(reminder.member_id)
    return ReminderOut(id=reminder.id, client_id=reminder.client_id or f'reminder-{reminder.id}',
                       member_client_id=(member.client_id or f'member-{member.id}') if member else None,
                       member_id=member.id if member else None, title=reminder.title, type=reminder.type,
                       date=reminder.date, advance=reminder.advance, repeat=reminder.repeat,
                       calendar=reminder.calendar, lunar_month=reminder.lunar_month,
                       lunar_day=reminder.lunar_day, lunar_leap=reminder.lunar_leap)


def snapshot(db: Session, family: Family, user: User, *, current_read: bool = False) -> SyncOut:
    if current_read:
        # 邀请码事务此前可能已有 MySQL RR read view；版本和资料统一锁读当前版本。
        family = db.scalar(select(Family).where(Family.id == family.id).with_for_update()
                           .execution_options(populate_existing=True))
        if not family:
            raise HTTPException(status_code=404, detail='家族不存在')
        member_query = select(FamilyMember).where(FamilyMember.family_id == family.id,
                                                 FamilyMember.deleted_at.is_(None)).order_by(FamilyMember.id)
        members = db.scalars(member_query.with_for_update(read=True)
                             .execution_options(populate_existing=True)).all()
        if family.owner_id == user.id:
            role = 'OWNER'
        else:
            membership = db.scalar(select(FamilyMembership).where(
                FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id)
                .with_for_update(read=True).execution_options(populate_existing=True))
            if not membership:
                raise HTTPException(status_code=403, detail='没有该家族的访问权限')
            role = 'VIEWER' if membership.role == 'VIEWER' else 'EDITOR'
    else:
        members = active_members(db, family.id)
        role = role_for(db, family, user)
    by_id = {member.id: member for member in members}
    reminder_query = select(Reminder).where(Reminder.family_id == family.id).order_by(Reminder.id)
    if current_read:
        reminder_query = reminder_query.with_for_update(read=True).execution_options(populate_existing=True)
    reminders = db.scalars(reminder_query).all()
    return SyncOut(family_id=family.id, revision=family.revision, role=role,
                   profile=FamilyProfile(name=family.name, avatar=family.avatar),
                   members=[member_out(member, by_id) for member in members],
                   reminders=[reminder_out(reminder, by_id) for reminder in reminders],
                   warnings=graph_warnings([member_out(member, by_id) for member in members]))


def audit(db: Session, user: User, family: Family, action: str, target_type='family', target_id=None, changes=''):
    db.add(AuditLog(user_id=user.id, family_id=family.id, action=action, target_type=target_type,
                    target_id=str(target_id if target_id is not None else family.id), changes=changes))


def graph_warnings(members):
    by_key = {m.client_id: m for m in members}
    warnings = []
    for member in members:
        for parent_key in member.parent_client_ids:
            parent = by_key.get(parent_key)
            if not parent:
                continue
            problems = []
            if parent.generation >= member.generation:
                problems.append('父母世代不早于子女')
            py = parent.birth_year or (int(parent.birthday[:4]) if parent.birthday else None)
            cy = member.birth_year or (int(member.birthday[:4]) if member.birthday else None)
            if py and cy and py >= cy:
                problems.append('父母出生年份不早于子女')
            if problems:
                warnings.append(f'{member.name} / {parent.name}：{"；".join(problems)}' +
                                (f'（例外说明：{member.relationship_note}）' if member.relationship_note else '，请核对或补充收养、继亲及例外说明'))
    return warnings


def reserve_revision(db: Session, family: Family, user: User, revision: int):
    # FOR UPDATE 在 MySQL 中串行化读；条件 UPDATE 同时保护 SQLite 和任何并发客户端。
    locked = db.scalar(select(Family).where(Family.id == family.id).with_for_update().execution_options(populate_existing=True))
    if locked.revision != revision:
        remote = snapshot(db, locked, user).model_dump(mode='json')
        raise HTTPException(status_code=409, detail={'message': '家谱已有新版本，请核对后合并再保存', 'remote': remote})
    result = db.execute(update(Family).where(Family.id == family.id, Family.revision == revision).values(revision=revision + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        db.refresh(family)
        raise HTTPException(status_code=409, detail={'message': '家谱已有新版本，请重新同步', 'remote': snapshot(db, family, user).model_dump(mode='json')})
    family.revision = revision + 1


def _validate_graph(payload: SyncData, current_members, current_reminders):
    by_db = {member.id: member.client_id or f'member-{member.id}' for member in current_members}
    keys = [member.client_id for member in payload.members]
    reminder_keys = [reminder.client_id for reminder in payload.reminders]
    if any(not key for key in keys + reminder_keys):
        raise HTTPException(status_code=422, detail='成员和纪念日必须有稳定的 client_id')
    if len(set(keys)) != len(keys) or len(set(reminder_keys)) != len(reminder_keys):
        raise HTTPException(status_code=422, detail='client_id 不能重复')
    if sum(member.relation == '本人' for member in payload.members) > 1:
        raise HTTPException(status_code=422, detail='每份家谱只能有一位本人')
    members = {member.client_id: member.model_copy(deep=True) for member in payload.members}
    for key, member in members.items():
        if member.parent_ids and not member.parent_client_ids:
            if any(parent not in by_db for parent in member.parent_ids):
                raise HTTPException(status_code=422, detail='父母关联成员不存在')
            member.parent_client_ids = [by_db[parent] for parent in member.parent_ids]
        if member.spouse_id is not None and not member.spouse_client_id:
            if member.spouse_id not in by_db:
                raise HTTPException(status_code=422, detail='配偶关联成员不存在')
            member.spouse_client_id = by_db[member.spouse_id]
        parents = member.parent_client_ids
        if member.parent_roles and len(member.parent_roles) != len(parents):
            raise HTTPException(status_code=422, detail='父母角色数量须与关联父母数量一致')
        if member.parent_roles.count('father') > 1 or member.parent_roles.count('mother') > 1:
            raise HTTPException(status_code=422, detail='父亲和母亲角色不能重复')
        if len(set(parents)) != len(parents):
            raise HTTPException(status_code=422, detail='父母不能重复')
        if key in parents or key == member.spouse_client_id:
            raise HTTPException(status_code=422, detail='成员不能与自己建立关系')
        if any(parent not in members for parent in parents) or (member.spouse_client_id and member.spouse_client_id not in members):
            raise HTTPException(status_code=422, detail='关联成员不存在于当前家谱')
        if member.spouse_client_id in parents:
            raise HTTPException(status_code=422, detail='父母不能同时是配偶')
        history_keys = [link.id for link in member.history_links]
        if len(set(history_keys)) != len(history_keys):
            raise HTTPException(status_code=422, detail='历史关系编号不能重复')
        for link in member.history_links:
            if link.member_client_id == key or link.member_client_id not in members:
                raise HTTPException(status_code=422, detail='历史关系须关联当前家谱的另一位成员')
    # 配偶关系归一化为双向；一边未选择时补齐，两边选择矛盾时拒绝。
    for key, member in members.items():
        spouse_key = member.spouse_client_id
        if not spouse_key:
            continue
        spouse = members[spouse_key]
        if spouse.spouse_client_id and spouse.spouse_client_id != key:
            raise HTTPException(status_code=422, detail='所选成员已有另一位配偶')
        spouse.spouse_client_id = key
    # 使用拓扑排序避免 10,000 人族谱超过递归栈，同时识别完整循环。
    children = {key: [] for key in members}
    ancestry = {key: set(member.parent_client_ids) | {link.member_client_id for link in member.history_links
                if link.kind in {'biological_parent', 'adoptive_parent', 'step_parent'}} for key, member in members.items()}
    indegree = {key: len(parents) for key, parents in ancestry.items()}
    for key, member in members.items():
        for parent in ancestry[key]:
            children[parent].append(key)
    ready = [key for key, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        key = ready.pop()
        visited += 1
        for child in children[key]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if visited != len(members):
        raise HTTPException(status_code=422, detail='父母关系会形成循环世系')
    # 配偶不得是直系祖先或后代。
    for key, member in members.items():
        if not member.spouse_client_id and not any(link.kind == 'marriage' for link in member.history_links):
            continue
        spouses = {member.spouse_client_id} | {link.member_client_id for link in member.history_links if link.kind == 'marriage'}
        seen, stack = set(), list(ancestry[key])
        while stack:
            parent = stack.pop()
            if parent in spouses:
                raise HTTPException(status_code=422, detail='直系祖先与后代不能建立配偶关系')
            if parent not in seen:
                seen.add(parent)
                stack.extend(ancestry[parent])
    reminders = []
    for reminder in payload.reminders:
        reminder = reminder.model_copy(deep=True)
        if reminder.member_id is not None and not reminder.member_client_id:
            if reminder.member_id not in by_db:
                raise HTTPException(status_code=422, detail='提醒关联成员不存在')
            reminder.member_client_id = by_db[reminder.member_id]
        if reminder.member_client_id and reminder.member_client_id not in members:
            raise HTTPException(status_code=422, detail='提醒关联成员不存在于当前家谱')
        reminders.append(reminder)
    return members, reminders


def replace_relationships(db: Session, family_id: int, members):
    db.execute(delete(FamilyRelationship).where(FamilyRelationship.family_id == family_id))
    for member in members:
        for parent in json.loads(member.parent_ids or '[]'):
            db.add(FamilyRelationship(family_id=family_id, from_member_id=parent, to_member_id=member.id, kind='parent'))
        if member.spouse_id and member.id < member.spouse_id:
            db.add(FamilyRelationship(family_id=family_id, from_member_id=member.id, to_member_id=member.spouse_id, kind='spouse'))


def save_snapshot(db: Session, user: User, payload: SyncData, action='family.sync') -> SyncOut:
    family = family_for(db, user, payload.family_id, write=True)
    if action in {'family.import', 'family.clear', 'family.restore'} and role_for(db, family, user) != 'OWNER':
        raise HTTPException(status_code=403, detail='只有管理员可以清空、覆盖导入或恢复整份家谱')
    # 只允许目标家族的明确快照。切换家族后的迟到请求不会误写 active 家族。
    current_members = db.scalars(select(FamilyMember).where(FamilyMember.family_id == family.id)).all()
    current_reminders = db.scalars(select(Reminder).where(Reminder.family_id == family.id)).all()
    graph, reminders = _validate_graph(payload, [m for m in current_members if m.deleted_at is None], current_reminders)
    removed = sum(m.deleted_at is None and m.client_id not in graph for m in current_members)
    removed += sum(r.client_id not in {item.client_id for item in reminders} for r in current_reminders)
    if role_for(db, family, user) != 'OWNER' and (removed > 1 or
            (removed and not graph and not reminders)):
        raise HTTPException(status_code=403, detail='批量删除或清空家谱需要管理员权限')
    reserve_revision(db, family, user, payload.revision)
    before = snapshot(db, family, user).model_dump(mode='json')
    before['revision'] = payload.revision
    db.add(FamilyVersion(family_id=family.id, user_id=user.id, revision=payload.revision,
                         action=action, data=json.dumps(before, ensure_ascii=False)))
    family.name, family.avatar = payload.profile.name, payload.profile.avatar
    existing = {member.client_id or f'member-{member.id}': member for member in current_members}
    saved = {}
    plain_fields = ['name', 'relation', 'gender', 'generation', 'birthday', 'birth_year', 'birth_month', 'birth_approximate',
                    'relationship_note', 'death_year', 'death_date', 'deceased', 'avatar_label', 'avatar_name', 'bio']
    for key, item in graph.items():
        member = existing.get(key)
        if member is None:
            member = FamilyMember(family_id=family.id, client_id=key)
            db.add(member)
            audit(db, user, family, 'member.create', 'member', key)
        elif any(getattr(member, field) != getattr(item, field) for field in plain_fields) or member.deleted_at is not None:
            audit(db, user, family, 'member.update', 'member', key)
        member.client_id = key
        member.deleted_at = None
        for field in plain_fields:
            setattr(member, field, getattr(item, field))
        member.history_links = json.dumps([link.model_dump() for link in item.history_links], ensure_ascii=False)
        saved[key] = member
    db.flush()
    for key, member in saved.items():
        item = graph[key]
        parent_ids = [saved[parent].id for parent in item.parent_client_ids]
        spouse_id = saved[item.spouse_client_id].id if item.spouse_client_id else None
        if (json.loads(member.parent_ids or '[]') != parent_ids
                or json.loads(member.parent_roles or '[]') != item.parent_roles
                or member.spouse_id != spouse_id):
            audit(db, user, family, 'member.relationships', 'member', key)
        member.parent_ids = json.dumps(parent_ids)
        member.parent_roles = json.dumps(item.parent_roles)
        member.spouse_id = spouse_id
    now = datetime.utcnow()
    for key, member in existing.items():
        if key not in graph and member.deleted_at is None:
            member.deleted_at = now
            member.parent_ids, member.parent_roles, member.spouse_id = '[]', '[]', None
            audit(db, user, family, 'member.delete', 'member', key)
    reminder_rows = {row.client_id or f'reminder-{row.id}': row for row in current_reminders}
    reminder_fields = ['title', 'type', 'date', 'advance', 'repeat', 'calendar', 'lunar_month', 'lunar_day', 'lunar_leap']
    for item in reminders:
        row = reminder_rows.pop(item.client_id, None)
        member_id = saved[item.member_client_id].id if item.member_client_id else None
        if row is None:
            row = Reminder(family_id=family.id, client_id=item.client_id)
            db.add(row)
            audit(db, user, family, 'reminder.create', 'reminder', item.client_id)
        elif row.member_id != member_id or any(getattr(row, field) != getattr(item, field) for field in reminder_fields):
            cancel_reminder_notifications(db, row.id)
            audit(db, user, family, 'reminder.update', 'reminder', item.client_id)
        row.client_id, row.member_id = item.client_id, member_id
        for field in reminder_fields:
            setattr(row, field, getattr(item, field))
    for row in reminder_rows.values():
        cancel_reminder_notifications(db, row.id)
        db.delete(row)
        audit(db, user, family, 'reminder.delete', 'reminder', row.client_id)
    replace_relationships(db, family.id, saved.values())
    db.flush()
    after = snapshot(db, family, user).model_dump(mode='json')
    # 完整内容保存在版本库，日志记录操作者和变化对象，避免把私人长文本重复写入日志。
    changes = json.dumps({'profile': before['profile'] != after['profile'],
        'members': [m['client_id'] for m in after['members'] if m not in before['members']],
        'deleted_members': [m['client_id'] for m in before['members'] if m['client_id'] not in graph],
        'reminders_changed': before['reminders'] != after['reminders'], 'previous_revision': payload.revision}, ensure_ascii=False)
    audit(db, user, family, action, changes=changes)
    db.commit()
    return snapshot(db, family, user)


def cancel_reminder_notifications(db: Session, reminder_id: int):
    from app.models import NotificationRecord, WechatDelivery
    # 所有未确认投递的通道失效，历史收件箱保留。指纹使正在投递的 worker 也能再次核验。
    db.execute(update(NotificationRecord).where(NotificationRecord.reminder_id == reminder_id).values(source_fingerprint='cancelled'))
    for field, sent in [(NotificationRecord.push_status, ['SENT', 'PARTIAL']),
                        (NotificationRecord.mobile_status, ['ACCEPTED', 'PARTIAL'])]:
        db.execute(update(NotificationRecord).where(NotificationRecord.reminder_id == reminder_id,
                   field.not_in(sent)).values({field.key: 'CANCELLED'}))
    ids = select(NotificationRecord.id).where(NotificationRecord.reminder_id == reminder_id)
    db.execute(update(WechatDelivery).where(WechatDelivery.notification_id.in_(ids),
               WechatDelivery.status.not_in(['ACCEPTED', 'UNKNOWN'])).values(status='CANCELLED'))


def snapshot_payload(db: Session, user: User, family: Family, revision: Optional[int] = None) -> SyncData:
    current = snapshot(db, family, user)
    return SyncData(family_id=current.family_id, revision=family.revision if revision is None else revision,
                    profile=current.profile, members=current.members, reminders=current.reminders)


def new_client_id(prefix: str) -> str:
    return f'{prefix}-{uuid4().hex}'
