from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


FamilyRole = Literal['OWNER', 'EDITOR', 'VIEWER']


class FamilyProfile(BaseModel):
    name: str = Field(default='我的家谱', min_length=1, max_length=64)
    avatar: str = Field(default='', max_length=2_800_000)

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class HistoryLink(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    member_client_id: str = Field(..., min_length=1, max_length=64)
    kind: Literal['marriage', 'biological_parent', 'adoptive_parent', 'step_parent', 'guardian']
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    note: str = Field(default='', max_length=500)

    @model_validator(mode='after')
    def valid_period(self):
        for value in (self.start_date, self.end_date):
            if value:
                date.fromisoformat(value)
                if value > date.today().isoformat():
                    raise ValueError('关系起止日期不能晚于今天')
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError('关系结束日期不能早于开始日期')
        return self


class MemberPayload(BaseModel):
    client_id: str = Field(default='', max_length=64)
    parent_client_ids: list[str] = Field(default_factory=list, max_length=2)
    # 与父母 ID 按位置对应；空列表保留旧数据尚未指定角色的含义。
    parent_roles: list[Literal['father', 'mother', 'parent']] = Field(default_factory=list, max_length=2)
    spouse_client_id: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    relation: str = Field(default='其他亲属', max_length=32)
    gender: Literal['男', '女', '未知'] = '未知'
    generation: int = Field(default=3, ge=1, le=100)
    birthday: Optional[str] = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    birth_year: Optional[int] = Field(default=None, ge=1, le=9999)
    birth_month: Optional[int] = Field(default=None, ge=1, le=12)
    birth_approximate: bool = False
    history_links: list[HistoryLink] = Field(default_factory=list, max_length=100)
    relationship_note: str = Field(default='', max_length=500)
    death_year: Optional[str] = Field(default=None, pattern=r'^\d{4}$')
    death_date: Optional[str] = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    deceased: bool = False
    avatar_label: str = Field(default='', max_length=8)
    avatar_name: str = Field(default='', max_length=32)
    bio: str = Field(default='', max_length=2000)
    parent_ids: list[int] = Field(default_factory=list, max_length=2)
    spouse_id: Optional[int] = None

    @field_validator('name', 'relation', 'avatar_label', 'avatar_name', 'bio', 'client_id', mode='before')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('death_year', mode='before')
    @classmethod
    def normalize_death_year(cls, value):
        return None if value in (None, '') else str(value)

    @field_validator('birthday', 'death_date')
    @classmethod
    def valid_birthday(cls, value):
        if value:
            date.fromisoformat(value)
            if value > date.today().isoformat():
                raise ValueError('生卒日期不能晚于今天')
        return value

    @model_validator(mode='after')
    def valid_parent_roles(self):
        parents = self.parent_client_ids or self.parent_ids
        if self.parent_roles and len(self.parent_roles) != len(parents):
            raise ValueError('父母角色数量须与关联父母数量一致')
        if self.parent_roles.count('father') > 1 or self.parent_roles.count('mother') > 1:
            raise ValueError('父亲和母亲角色不能重复')
        return self

    @model_validator(mode='after')
    def valid_lifetime(self):
        if self.birthday:
            y, m = int(self.birthday[:4]), int(self.birthday[5:7])
            if self.birth_year is not None and self.birth_year != y:
                raise ValueError('出生年份与出生日期不一致')
            if self.birth_month is not None and self.birth_month != m:
                raise ValueError('出生月份与出生日期不一致')
            self.birth_year, self.birth_month = y, m
        if self.birth_month and not self.birth_year:
            raise ValueError('出生月份需要同时填写年份')
        if self.birth_year and (self.birth_year > date.today().year or
                (self.birth_year == date.today().year and self.birth_month and self.birth_month > date.today().month)):
            raise ValueError('出生年月不能晚于今天')
        if self.death_date:
            if self.birthday and self.death_date < self.birthday:
                raise ValueError('忌日不能早于生日')
            if self.death_year and self.death_year != self.death_date[:4]:
                raise ValueError('卒年与忌日年份不一致')
            self.death_year = self.death_date[:4]
        if self.death_year and self.birth_year and int(self.death_year) < self.birth_year:
            raise ValueError('卒年不能早于出生年份')
        if self.death_year and int(self.death_year) > date.today().year:
            raise ValueError('卒年不能晚于今年')
        if self.death_year and not self.deceased:
            self.deceased = True
        return self


class MemberOut(MemberPayload):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReminderPayload(BaseModel):
    client_id: str = Field(default='', max_length=64)
    member_client_id: Optional[str] = Field(default=None, max_length=64)
    title: str = Field(..., min_length=1, max_length=128)
    type: str = Field(default='生日', max_length=32)
    member_id: Optional[int] = None
    date: str = Field(..., pattern=r'^\d{4}-\d{2}-\d{2}$')
    advance: Literal['当天', '提前1天', '提前3天', '提前7天', '提前15天'] = '当天'
    repeat: Literal['每年', '仅一次'] = '每年'
    calendar_type: Literal['solar', 'lunar', 'qingming'] = 'solar'
    lunar_month: Optional[int] = Field(default=None, ge=1, le=12)
    lunar_day: Optional[int] = Field(default=None, ge=1, le=30)
    is_leap: bool = False

    @model_validator(mode='before')
    @classmethod
    def calendar_aliases(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            if 'calendar_type' not in value and 'calendar' in value:
                value['calendar_type'] = value['calendar']
            if 'is_leap' not in value and 'lunar_leap' in value:
                value['is_leap'] = value['lunar_leap']
        return value

    @property
    def calendar(self):
        return self.calendar_type

    @property
    def lunar_leap(self):
        return self.is_leap

    @field_validator('title', 'type', 'advance', 'repeat', 'client_id', mode='before')
    @classmethod
    def strip_text(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value == '不重复':
            return '仅一次'
        return value.replace('提前 ', '提前').replace(' 天', '天')

    @field_validator('date')
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def lunar_fields(self):
        if self.calendar == 'lunar' and (self.lunar_month is None or self.lunar_day is None):
            raise ValueError('农历纪念日需要农历月、日')
        return self


class ReminderOut(ReminderPayload):
    model_config = ConfigDict(from_attributes=True)
    id: int


class SyncData(BaseModel):
    family_id: int = Field(..., gt=0)
    revision: int = Field(..., ge=0)
    profile: FamilyProfile = Field(default_factory=FamilyProfile)
    members: list[MemberPayload] = Field(default_factory=list, max_length=10000)
    reminders: list[ReminderPayload] = Field(default_factory=list, max_length=10000)


class SyncOut(BaseModel):
    family_id: int
    revision: int
    role: FamilyRole
    profile: FamilyProfile
    members: list[MemberOut]
    reminders: list[ReminderOut]
    warnings: list[str] = Field(default_factory=list)


class ActiveFamilyPayload(BaseModel):
    family_id: int = Field(..., gt=0)


class FamilySummary(BaseModel):
    id: int
    owner_id: int
    name: str
    avatar: str
    role: FamilyRole
    revision: int
    active: bool
    personal: bool = False


class InvitePayload(BaseModel):
    invitee: str = Field(..., min_length=1, max_length=64)
    role: Literal['EDITOR', 'VIEWER'] = 'EDITOR'

    @field_validator('invitee', mode='before')
    @classmethod
    def strip_invitee(cls, value):
        return value.strip() if isinstance(value, str) else value


class InviteOut(BaseModel):
    id: int
    family_id: int
    family_name: str
    inviter: str
    invitee: str
    role: str
    status: str
    expires_at: Optional[datetime]


class MembershipPayload(BaseModel):
    role: Literal['EDITOR', 'VIEWER']


class MembershipOut(BaseModel):
    id: int
    user_id: int
    username: str
    role: FamilyRole


class AuditOut(BaseModel):
    id: int
    user_id: Optional[int]
    username: str
    action: str
    target_type: str
    target_id: str
    created_at: datetime
    changes: str = ''


class TransferPayload(BaseModel):
    user_id: int = Field(..., gt=0)
    revision: int = Field(..., ge=0)


class RestorePayload(BaseModel):
    revision: int = Field(..., ge=0)
