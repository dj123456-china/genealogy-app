from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import bearer, get_current_user
from app.core.security import token_fingerprint
from app.db.session import get_db
from app.models import User, UserSession
from app.models.wechat import WechatDevice
from app.services.wechat_push import configuration, exchange_code
import hashlib
router=APIRouter(prefix='/notifications',tags=['微信通知'])
class Registration(BaseModel):
    code: str = Field(min_length=1,max_length=256)

@router.post('/wechat-devices',status_code=201)
def register(payload:Registration,user:User=Depends(get_current_user),credentials=Depends(bearer),db:Session=Depends(get_db)):
    config=configuration()
    if not config['configured']: raise HTTPException(503,'尚未配置微信订阅消息服务')
    try: open_id=exchange_code(payload.code,config)
    except Exception as error: raise HTTPException(502,'微信授权验证失败，请重新授权') from error
    fingerprint=hashlib.sha256((config['app_id']+':'+open_id).encode()).hexdigest()
    device=db.scalar(select(WechatDevice).where(WechatDevice.device_hash==fingerprint).with_for_update())
    session_id=db.scalar(select(UserSession.id).where(UserSession.token_hash==token_fingerprint(credentials.credentials),UserSession.user_id==user.id,UserSession.revoked_at.is_(None),UserSession.expires_at>datetime.utcnow()))
    if not session_id: raise HTTPException(401,'登录会话已撤销或过期，请重新登录')
    if not device:
        device=WechatDevice(user_id=user.id,session_id=session_id,app_id=config['app_id'],open_id=open_id,device_hash=fingerprint,allowance=0)
        db.add(device)
    if device.user_id!=user.id: device.allowance=0
    device.user_id=user.id;device.session_id=session_id;device.allowance=min(100,device.allowance+1)
    try: db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409,'微信设备登记发生并发冲突，请重新授权') from error
    return {'id':device.id,'message':'已登记一次微信订阅授权，消息实际投递以微信权限为准。'}

@router.delete('/wechat-devices/{device_id}')
def unregister(device_id:int,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    device=db.get(WechatDevice,device_id)
    if not device or device.user_id!=user.id: raise HTTPException(404,'微信订阅设备不存在')
    db.delete(device);db.commit()
    return {'message':'微信订阅已撤销'}
