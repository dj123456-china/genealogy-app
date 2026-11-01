"""七天、单次家族邀请码；消费与成员资格/个人谱/切换原子提交。"""
from datetime import datetime, timedelta
import hashlib
import hmac
import secrets

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import Family, FamilyMembership, User
from app.models.invite_code import FamilyInviteCode, InviteCodeRateLimit
from app.services.family import audit, snapshot

INVALID_CODE = '邀请码无效、已使用或已过期，请向家族管理员索取新码'
RATE_WINDOW = timedelta(minutes=15)


def locked_user(db: Session, user: User) -> User:
    current = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    if not current:
        raise HTTPException(status_code=401, detail='账号已不存在，请重新登录')
    return current


def owner_family(db: Session, user: User, family_id: int) -> Family:
    family = db.scalar(select(Family).where(Family.id == family_id).with_for_update().execution_options(populate_existing=True))
    if not family:
        raise HTTPException(status_code=404, detail='家族不存在')
    if family.owner_id != user.id:
        raise HTTPException(status_code=403, detail='只有家族管理员可以管理邀请码')
    return family


def ensure_personal_family(db: Session, user: User) -> Family:
    """只确保独立个人谱，不读取 active_family_id，不覆盖任何已有家谱。"""
    family = db.scalar(select(Family).where(Family.owner_id == user.id, Family.personal_owner_id == user.id))
    # 兼容尚未写入 personal_owner_id 的旧个人谱。只有该账号是唯一协作者时
    # 才可安全认定为个人谱；共享家谱会保留其他成员资格，不会被误认领。
    if not family:
        candidates = db.scalars(select(Family).where(
            Family.owner_id == user.id, Family.personal_owner_id.is_(None))).all()
        for candidate in candidates:
            member_ids = set(db.scalars(select(FamilyMembership.user_id).where(
                FamilyMembership.family_id == candidate.id)).all())
            if member_ids <= {user.id}:
                family = candidate
                family.personal_owner_id = user.id
                break
    if not family:
        try:
            with db.begin_nested():
                family = Family(owner_id=user.id, personal_owner_id=user.id)
                db.add(family)
                db.flush()
        except IntegrityError:
            # MySQL REPEATABLE READ 的普通查询可能仍保留竞争前快照。
            family = db.scalar(select(Family).where(Family.personal_owner_id == user.id).with_for_update())
            if not family:
                raise
    membership = db.scalar(select(FamilyMembership).where(
        FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id))
    if not membership:
        try:
            with db.begin_nested():
                db.add(FamilyMembership(family_id=family.id, user_id=user.id, role='OWNER'))
                db.flush()
        except IntegrityError:
            existing = db.scalar(select(FamilyMembership).where(
                FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id).with_for_update())
            if not existing:
                raise
    return family


def _reserve_bucket(db: Session, key: str, user_id, maximum: int, now: datetime) -> datetime:
    for _ in range(8):
        row = db.scalar(select(InviteCodeRateLimit).where(InviteCodeRateLimit.key == key)
                        .with_for_update().execution_options(populate_existing=True))
        if not row:
            try:
                with db.begin_nested():
                    db.add(InviteCodeRateLimit(key=key, user_id=user_id, window_started_at=now, attempts=0))
                    db.flush()
            except IntegrityError:
                pass
            continue
        window = row.window_started_at
        if window <= now - RATE_WINDOW:
            reset = db.execute(update(InviteCodeRateLimit).where(
                InviteCodeRateLimit.key == key, InviteCodeRateLimit.window_started_at == window,
            ).values(window_started_at=now, attempts=1).execution_options(synchronize_session=False))
            if reset.rowcount == 1:
                return now
            continue
        if row.attempts >= maximum:
            raise HTTPException(status_code=429, detail='邀请码尝试次数过多，请15分钟后再试', headers={'Retry-After': '900'})
        reserved = db.execute(update(InviteCodeRateLimit).where(
            InviteCodeRateLimit.key == key, InviteCodeRateLimit.window_started_at == window,
            InviteCodeRateLimit.attempts < maximum,
        ).values(attempts=InviteCodeRateLimit.attempts + 1).execution_options(synchronize_session=False))
        if reserved.rowcount == 1:
            return window
    raise HTTPException(status_code=429, detail='请求过于频繁，请稍后再试')


def reserve_join_attempt(db: Session, user_id: int, network_address: str):
    # 使用可信 ASGI 客户端地址；不接受客户端自填的 X-Forwarded-For。
    digest = hmac.new(settings.secret_key.encode(), network_address.encode(), hashlib.sha256).hexdigest()
    buckets = [(f'network:{digest}', None, 30), (f'user:{user_id}', user_id, 5)]
    # MySQL DATETIME 默认只有秒精度；退款的窗口键必须与数据库存值一致。
    now = datetime.utcnow().replace(microsecond=0)
    try:
        reserved = [(key, _reserve_bucket(db, key, owner, maximum, now))
                    for key, owner, maximum in buckets]
        db.commit()
        return reserved
    except Exception:
        db.rollback()
        raise


def refund_join_attempt(db: Session, reserved):
    # 请求成功后仅退还原窗口次数，跨窗口完成不能扣减新窗口的失败计数。
    for key, window in reserved:
        db.execute(update(InviteCodeRateLimit).where(
            InviteCodeRateLimit.key == key, InviteCodeRateLimit.window_started_at == window,
            InviteCodeRateLimit.attempts > 0,
        ).values(attempts=InviteCodeRateLimit.attempts - 1).execution_options(synchronize_session=False))


def create_code(db: Session, user: User, family_id: int, role: str):
    if role not in {'EDITOR', 'VIEWER'}:
        raise HTTPException(status_code=422, detail='邀请码仅可授予编辑或只读权限')
    user = locked_user(db, user)
    family = owner_family(db, user, family_id)
    now = datetime.utcnow()
    # 有效码上限与创建频率一起限制号码空间滥用，历史码仍保持全局唯一。
    active = db.scalar(select(func.count()).select_from(FamilyInviteCode).where(
        FamilyInviteCode.family_id == family.id, FamilyInviteCode.status == 'PENDING', FamilyInviteCode.expires_at > now))
    recent = db.scalar(select(func.count()).select_from(FamilyInviteCode).where(
        FamilyInviteCode.inviter_id == user.id, FamilyInviteCode.created_at > now - timedelta(hours=1)))
    if active >= 10 or recent >= 20:
        raise HTTPException(status_code=429, detail='邀请码生成次数过多，请先撤销未使用的码或稍后再试')
    for _ in range(40):
        try:
            with db.begin_nested():
                row = FamilyInviteCode(code=f'{secrets.randbelow(1_000_000):06d}', family_id=family.id,
                                       inviter_id=user.id, role=role, expires_at=now + timedelta(days=7), created_at=now)
                db.add(row)
                db.flush()
            audit(db, user, family, 'invite_code.create', 'invite_code', row.id)
            db.commit()
            return row
        except IntegrityError:
            continue
    db.rollback()
    raise HTTPException(status_code=503, detail='暂时无法生成邀请码，请稍后再试')


def list_codes(db: Session, user: User, family_id: int):
    user = locked_user(db, user)
    family = owner_family(db, user, family_id)
    db.execute(update(FamilyInviteCode).where(
        FamilyInviteCode.family_id == family.id, FamilyInviteCode.status == 'PENDING',
        FamilyInviteCode.expires_at <= datetime.utcnow(),
    ).values(status='EXPIRED'))
    rows = list(db.scalars(select(FamilyInviteCode).where(FamilyInviteCode.family_id == family.id)
                           .order_by(FamilyInviteCode.id.desc()).limit(100)))
    db.commit()
    return rows


def revoke_code(db: Session, user: User, code_id: int):
    user = locked_user(db, user)
    row = db.get(FamilyInviteCode, code_id)
    if not row:
        raise HTTPException(status_code=404, detail='邀请码不存在')
    family = owner_family(db, user, row.family_id)
    revoked = db.execute(update(FamilyInviteCode).where(
        FamilyInviteCode.id == row.id, FamilyInviteCode.status == 'PENDING',
        FamilyInviteCode.expires_at > datetime.utcnow(),
    ).values(status='CANCELLED'))
    if revoked.rowcount != 1:
        raise HTTPException(status_code=409, detail='邀请码已使用、撤销或过期')
    audit(db, user, family, 'invite_code.cancel', 'invite_code', row.id)
    db.commit()
    db.refresh(row)
    return row


def join_by_code(db: Session, user: User, code: str, network_address: str):
    # 首次限流落库前也锁定当前账号，避免注销后从迟到请求重建用户桶。
    user = locked_user(db, user)
    reserved = reserve_join_attempt(db, user.id, network_address)
    try:
        user = locked_user(db, user)
        row = db.scalar(select(FamilyInviteCode).where(FamilyInviteCode.code == code))
        if not row:
            raise HTTPException(status_code=400, detail=INVALID_CODE)
        family = db.scalar(select(Family).where(Family.id == row.family_id)
                           .with_for_update().execution_options(populate_existing=True))
        now = datetime.utcnow()
        if not family or family.owner_id == user.id or row.role not in {'EDITOR', 'VIEWER'}:
            raise HTTPException(status_code=400, detail=INVALID_CODE)
        claimed = db.execute(update(FamilyInviteCode).where(
            FamilyInviteCode.id == row.id, FamilyInviteCode.status == 'PENDING',
            FamilyInviteCode.expires_at > now,
        ).values(status='USED', used_by_user_id=user.id, used_at=now))
        if claimed.rowcount != 1:
            raise HTTPException(status_code=400, detail=INVALID_CODE)
        ensure_personal_family(db, user)
        membership = db.scalar(select(FamilyMembership).where(
            FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id))
        if not membership:
            try:
                with db.begin_nested():
                    db.add(FamilyMembership(family_id=family.id, user_id=user.id, role=row.role))
                    db.flush()
            except IntegrityError:
                membership = db.scalar(select(FamilyMembership).where(
                    FamilyMembership.family_id == family.id, FamilyMembership.user_id == user.id).with_for_update())
                if not membership:
                    raise
        # 已有成员资格原样保留；消费 EDITOR 码不能升级 VIEWER。
        user.active_family_id = family.id
        audit(db, user, family, 'invite_code.join', 'invite_code', row.id)
        refund_join_attempt(db, reserved)
        db.flush()
        result = snapshot(db, family, user, current_read=True)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def select_personal_family(db: Session, user: User):
    try:
        user = locked_user(db, user)
        family = ensure_personal_family(db, user)
        user.active_family_id = family.id
        audit(db, user, family, 'family.select_personal')
        db.flush()
        result = snapshot(db, family, user, current_read=True)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def delete_invite_code_data(db: Session, user_id: int, owned_family_ids):
    db.execute(delete(FamilyInviteCode).where(or_(
        FamilyInviteCode.family_id.in_(owned_family_ids), FamilyInviteCode.inviter_id == user_id,
        FamilyInviteCode.used_by_user_id == user_id,
    )))
    db.execute(delete(InviteCodeRateLimit).where(InviteCodeRateLimit.user_id == user_id))
