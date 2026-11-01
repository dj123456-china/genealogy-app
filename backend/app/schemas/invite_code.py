from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InviteCodePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['EDITOR', 'VIEWER'] = 'VIEWER'


class JoinByCodePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(..., strict=True, min_length=6, max_length=6, pattern=r'^[0-9]{6}$')


class InviteCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    family_id: int
    role: Literal['EDITOR', 'VIEWER']
    status: Literal['PENDING', 'USED', 'CANCELLED', 'EXPIRED']
    expires_at: datetime
