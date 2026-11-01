from pathlib import Path
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, Family, FileAsset, User
from app.services.assets import (active_asset_family, asset_directory, asset_path,
                                 can_read_asset, decode_image, delete_asset_files)

router = APIRouter(prefix='/assets', tags=['图片'])


class UploadImage(BaseModel):
    family_id: Optional[int] = Field(default=None, gt=0)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    data_base64: str = Field(min_length=1, max_length=2_800_000)


@router.post('', status_code=201)
def upload_image(payload: UploadImage, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data, content_type = decode_image(payload.data_base64, payload.content_type)
    asset = FileAsset(owner_id=user.id, family_id=active_asset_family(db, user, payload.family_id),
                      filename=Path(payload.filename.replace('\\', '/')).name,
                      content_type=content_type, url='')
    if not asset.filename or asset.filename in {'.', '..'}:
        raise HTTPException(status_code=422, detail='文件名不正确')
    db.add(asset)
    db.flush()
    asset.url = f'/api/assets/{asset.id}/content'
    asset.storage_path = f'{asset.id}.bin'
    asset.size_bytes = len(data)
    asset.sha256 = hashlib.sha256(data).hexdigest()
    path = asset_path(asset.id)
    temporary = path.with_suffix('.tmp')
    try:
        asset_directory().mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(data)
        temporary.replace(path)
        db.add(AuditLog(user_id=user.id, family_id=asset.family_id, action='asset_uploaded',
                        target_type='asset', target_id=str(asset.id)))
        db.commit()
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return {'id': asset.id, 'url': asset.url}


@router.get('/{asset_id}/content')
def image_content(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(FileAsset, asset_id)
    if not asset or not can_read_asset(db, user, asset):
        raise HTTPException(status_code=404, detail='图片不存在或无权访问')
    path = asset_path(asset_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail='图片文件不存在，请重新上传')
    return FileResponse(path, media_type=asset.content_type,
                        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.delete('/{asset_id}')
def delete_image(asset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    asset = db.get(FileAsset, asset_id)
    if not asset or asset.owner_id != user.id:
        raise HTTPException(status_code=404, detail='图片不存在或不属于当前账号')
    for family in db.scalars(select(Family).where(Family.avatar == asset.url)):
        family.avatar = ''
        family.revision += 1
    db.add(AuditLog(user_id=user.id, family_id=asset.family_id, action='asset_deleted',
                    target_type='asset', target_id=str(asset.id)))
    db.delete(asset)
    db.commit()
    delete_asset_files([asset_id])
    return {'message': '图片已删除'}
