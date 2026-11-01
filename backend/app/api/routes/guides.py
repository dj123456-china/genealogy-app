"""登录导览的今日关闭、永久关闭及重置，服务器按上海日期计算。"""
from datetime import date, datetime, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.guides import UserGuideSetting
from app.models.user import User

router = APIRouter(prefix='/auth/guides', tags=['用户导览'])
SHANGHAI = ZoneInfo('Asia/Shanghai')


class GuideSettingRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dismissal: Literal['today', 'permanent', 'reset']


class GuideSettingOut(BaseModel):
    permanently_hidden: bool
    dismissed_on: Optional[date]
    show_on_login: bool


def guide_today(now: Optional[datetime] = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(SHANGHAI).date()


def guide_result(setting: Optional[UserGuideSetting]) -> GuideSettingOut:
    permanent = bool(setting and setting.permanently_hidden)
    dismissed_on = setting.dismissed_on if setting else None
    return GuideSettingOut(permanently_hidden=permanent, dismissed_on=dismissed_on,
                           show_on_login=not permanent and dismissed_on != guide_today())


@router.get('', response_model=GuideSettingOut)
def read_guide_setting(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return guide_result(db.get(UserGuideSetting, user.id))


@router.put('', response_model=GuideSettingOut)
def save_guide_setting(payload: GuideSettingRequest, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    # 真正取得写锁：SQLite 不支持 FOR UPDATE；不改时间值，与注销事务串行。
    existing = db.execute(update(User).where(User.id == user.id)
                          .values(updated_at=User.updated_at)
                          .execution_options(synchronize_session=False))
    if existing.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=401, detail='账号已不存在，请重新登录')
    values = {'user_id': user.id, 'permanently_hidden': payload.dismissal == 'permanent',
              'dismissed_on': guide_today() if payload.dismissal == 'today' else None}
    changes = {key: value for key, value in values.items() if key != 'user_id'}
    changes['updated_at'] = datetime.utcnow()
    # 同一账号多设备首次设置也只会生成一条；最后提交的完整偏好生效。
    dialect = db.get_bind().dialect.name
    if dialect == 'mysql':
        statement = mysql_insert(UserGuideSetting).values(**values).on_duplicate_key_update(**changes)
    elif dialect == 'sqlite':
        statement = sqlite_insert(UserGuideSetting).values(**values).on_conflict_do_update(
            index_elements=['user_id'], set_=changes)
    else:
        raise RuntimeError('导览设置需要已支持的 MySQL 或 SQLite 数据库')
    db.execute(statement)
    setting = db.get(UserGuideSetting, user.id)
    db.refresh(setting)
    result = guide_result(setting)
    db.commit()
    return result
