"""微信订阅消息：一次授权对应一次供应商投递，不冒充永久推送权限。"""
from __future__ import annotations
from datetime import datetime, timedelta
import hashlib
import json
import os
import threading
import time
import requests
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from types import SimpleNamespace
from app.models import Family, NotificationRecord, User, UserSession
from app.models.wechat import WechatDevice, WechatDelivery

_CACHE = {}
_LOCK = threading.Lock()

class ProviderRejected(RuntimeError):
    pass

def configuration():
    app_id, secret, template = (os.getenv(key, '') for key in ('WECHAT_APP_ID', 'WECHAT_APP_SECRET', 'WECHAT_REMINDER_TEMPLATE_ID'))
    try:
        fields = json.loads(os.getenv('WECHAT_REMINDER_FIELDS', '{"thing1":"title","date2":"date","thing3":"family"}'))
        valid = isinstance(fields, dict) and bool(fields) and all(isinstance(k,str) and v in {'title','date','family','body'} for k,v in fields.items())
    except (ValueError, TypeError):
        fields, valid = {}, False
    return {'app_id':app_id, 'secret':secret, 'template_id':template, 'fields':fields, 'configured':bool(app_id and secret and template and valid)}

def _result(response):
    response.raise_for_status()
    data = response.json()
    if not isinstance(data,dict) or data.get('errcode',0):
        raise RuntimeError('微信服务拒绝请求（code=%s）' % (data.get('errcode','invalid') if isinstance(data,dict) else 'invalid'))
    return data

def exchange_code(code, config):
    data = _result(requests.get('https://api.weixin.qq.com/sns/jscode2session', params={'appid':config['app_id'],'secret':config['secret'],'js_code':code,'grant_type':'authorization_code'},timeout=10))
    if not isinstance(data.get('openid'),str) or not 1 <= len(data['openid']) <= 128:
        raise RuntimeError('微信服务未返回有效用户标识')
    return data['openid']

def access_token(config):
    key=(config['app_id'],config['secret'])
    with _LOCK:
        cached=_CACHE.get(key)
        if cached and cached[1] > time.time()+60: return cached[0]
        data=_result(requests.get('https://api.weixin.qq.com/cgi-bin/token',params={'grant_type':'client_credential','appid':key[0],'secret':key[1]},timeout=10))
        if not data.get('access_token'): raise RuntimeError('微信服务未返回访问凭证')
        _CACHE[key]=(data['access_token'],time.time()+int(data.get('expires_in',7200)))
        return data['access_token']

def send(device, notice, family_name, config):
    values={'title':notice.title,'date':notice.due_date or notice.created_at.date().isoformat(),'family':family_name,'body':notice.body}
    fields={key:{'value':values[source][:20] if key.startswith('thing') else values[source]} for key,source in config['fields'].items()}
    response=requests.post('https://api.weixin.qq.com/cgi-bin/message/subscribe/send',params={'access_token':access_token(config)},json={'touser':device.open_id,'template_id':config['template_id'],'page':'pages/index/index?notifications=1','data':fields},timeout=10)
    response.raise_for_status()
    data=response.json()
    if not isinstance(data,dict) or type(data.get('errcode')) is not int:
        raise RuntimeError('微信未返回明确的投递确认')
    if data['errcode'] != 0:
        raise ProviderRejected('微信拒绝订阅消息（code=%s）' % data['errcode'])
    return data

def status(db, user):
    config=configuration()
    devices=list(db.scalars(select(WechatDevice).join(UserSession,WechatDevice.session_id==UserSession.id).where(WechatDevice.user_id==user.id,WechatDevice.app_id==config['app_id'],UserSession.user_id==user.id,UserSession.revoked_at.is_(None),UserSession.expires_at>datetime.utcnow())))
    return {'supported':True,'configured':config['configured'],'enabled':user.notifications_enabled and user.system_notifications_enabled,'template_id':config['template_id'] if config['configured'] else None,'devices':len(devices),'allowance':sum(d.allowance for d in devices),'message':'微信订阅消息已配置，每次授权可接收一次提醒。' if config['configured'] else '未配置微信 AppID、AppSecret 和订阅模板，微信后台通知未启用。'}

def deliver(db: Session, now=None):
    from app.services.notification_access import can_receive_family_notification
    config=configuration()
    if not config['configured']: return 0
    now=now or datetime.utcnow()
    db.execute(update(WechatDelivery).where(WechatDelivery.status=='SENDING',WechatDelivery.attempted_at<now-timedelta(minutes=5)).values(status='UNKNOWN',error='投递请求被中断，无法确认供应商是否接收；不重复扣除订阅授权。'))
    db.commit()
    count=0
    eligible_users=select(WechatDevice.user_id).join(UserSession,WechatDevice.session_id==UserSession.id).where(WechatDevice.app_id==config['app_id'],WechatDevice.allowance>0,UserSession.user_id==WechatDevice.user_id,UserSession.revoked_at.is_(None),UserSession.expires_at>now)
    retry_due=or_(WechatDelivery.attempted_at.is_(None),WechatDelivery.attempted_at<now-timedelta(minutes=15))
    notices=list(db.scalars(select(NotificationRecord).outerjoin(WechatDelivery,WechatDelivery.notification_id==NotificationRecord.id).where(NotificationRecord.created_at >= now-timedelta(days=2),NotificationRecord.user_id.in_(eligible_users),or_(WechatDelivery.id.is_(None),WechatDelivery.status.in_(['PENDING','FAILED']) & retry_due)).order_by(NotificationRecord.id).limit(200)))
    for notice in notices:
        user=db.get(User,notice.user_id)
        if not user or not user.notifications_enabled or not user.system_notifications_enabled: continue
        delivery=db.scalar(select(WechatDelivery).where(WechatDelivery.notification_id==notice.id))
        if delivery and (delivery.status in {'ACCEPTED','SENDING'} or delivery.attempted_at and delivery.attempted_at > now-timedelta(minutes=15)): continue
        devices=list(db.scalars(select(WechatDevice).join(UserSession,WechatDevice.session_id==UserSession.id).where(WechatDevice.user_id==user.id,WechatDevice.app_id==config['app_id'],WechatDevice.allowance>0,UserSession.user_id==user.id,UserSession.revoked_at.is_(None),UserSession.expires_at>now)))
        if not devices: continue
        if not delivery:
            delivery=WechatDelivery(notification_id=notice.id,user_id=user.id,status='PENDING')
            try:
                with db.begin_nested():
                    db.add(delivery);db.flush()
            except IntegrityError:
                # 另一 worker 已创建投递记录；由后续一轮按状态重新读取。
                continue
        if not can_receive_family_notification(db,notice):
            delivery.status='CANCELLED';db.commit();continue
        device=devices[0]
        target=SimpleNamespace(id=device.id,user_id=device.user_id,session_id=device.session_id,app_id=device.app_id,open_id=device.open_id)
        previous,previous_attempt=delivery.status,delivery.attempted_at
        claimed=db.execute(update(WechatDelivery).where(WechatDelivery.id==delivery.id,WechatDelivery.status==previous,WechatDelivery.attempted_at==previous_attempt).values(status='SENDING',attempted_at=now))
        db.commit()
        if claimed.rowcount != 1: continue
        # 先保留一次授权；网络超时不重复消耗或假称送达，用户可再次授权。
        valid_sessions=select(UserSession.id).where(UserSession.user_id==notice.user_id,UserSession.revoked_at.is_(None),UserSession.expires_at>now)
        reserved=db.execute(update(WechatDevice).where(WechatDevice.id==target.id,WechatDevice.user_id==notice.user_id,WechatDevice.session_id==target.session_id,WechatDevice.session_id.in_(valid_sessions),WechatDevice.app_id==target.app_id,WechatDevice.allowance>0).values(allowance=WechatDevice.allowance-1))
        db.commit()
        if reserved.rowcount!=1:
            delivery.status='PENDING';db.commit();continue
        if not can_receive_family_notification(db,notice):
            delivery.status='CANCELLED';db.commit();continue
        try:
            family=db.get(Family,notice.family_id)
            send(target,notice,family.name if family else '家族',config)
            delivery.status='ACCEPTED';delivery.error=None;count+=1
        except ProviderRejected as error:
            delivery.status='FAILED';delivery.error=type(error).__name__
        except Exception as error:
            # 供应商可能已接收但响应丢失；不得自动重复发送或再次扣授权。
            delivery.status='UNKNOWN';delivery.error=type(error).__name__
        db.commit()
    return count
