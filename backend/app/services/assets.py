"""私有图片存储。下载始终经过账户/家族授权，不公开静态目录。"""
from __future__ import annotations
import base64
import binascii
import io
import os
from pathlib import Path
import warnings

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Family, FamilyMembership, FileAsset, User

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_FORMATS = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp', 'GIF': 'image/gif'}


def asset_directory() -> Path:
    configured = os.getenv('ASSET_STORAGE_DIR')
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2] / 'data' / 'assets'


def asset_path(asset_id: int) -> Path:
    return asset_directory() / f'{int(asset_id)}.bin'


def delete_asset_files(asset_ids: list[int]) -> None:
    for asset_id in asset_ids:
        asset_path(asset_id).unlink(missing_ok=True)


def decode_image(data_base64: str, content_type: str) -> tuple[bytes, str]:
    if len(data_base64) > 2_800_000:
        raise HTTPException(status_code=413, detail='图片不能超过 2 MiB')
    if data_base64.startswith('data:'):
        try:
            metadata, data_base64 = data_base64.split(',', 1)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail='图片编码格式不正确') from exc
        if metadata != f'data:{content_type};base64':
            raise HTTPException(status_code=422, detail='图片类型与编码不匹配')
    try:
        data = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail='图片 Base64 编码不正确') from exc
    if not data:
        raise HTTPException(status_code=422, detail='图片不能为空')
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail='图片不能超过 2 MiB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                detected = ALLOWED_FORMATS.get(image.format)
                if not detected or detected != content_type:
                    raise HTTPException(status_code=422, detail='仅支持 PNG、JPEG、WebP、GIF 图片，且类型须正确')
                if image.width > 8192 or image.height > 8192 or image.width * image.height > 24_000_000:
                    raise HTTPException(status_code=422, detail='图片尺寸过大，请缩小后上传')
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(status_code=422, detail='图片内容损坏或格式不支持') from exc
    return data, content_type


def active_asset_family(db: Session, user: User, family_id: int | None = None) -> int | None:
    explicit_family = family_id is not None
    family_id = family_id if explicit_family else user.active_family_id
    family = db.get(Family, family_id) if family_id else db.scalar(select(Family).where(Family.owner_id == user.id))
    if not family:
        if explicit_family:
            raise HTTPException(status_code=404, detail='家族不存在或已经删除')
        return None
    if family.owner_id != user.id:
        membership = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == family.id,
                                                             FamilyMembership.user_id == user.id))
        if not membership:
            raise HTTPException(status_code=403, detail='无权访问当前家族')
        if membership.role not in {'EDITOR', 'OWNER'}:
            raise HTTPException(status_code=403, detail='只读成员不能上传家族图片')
    return family.id


def can_read_asset(db: Session, user: User, asset: FileAsset) -> bool:
    if asset.owner_id == user.id:
        return True
    if asset.family_id:
        family = db.get(Family, asset.family_id)
        if family and family.owner_id == user.id:
            return True
        return db.scalar(select(FamilyMembership.id).where(FamilyMembership.family_id == asset.family_id,
                                                           FamilyMembership.user_id == user.id)) is not None
    return False
