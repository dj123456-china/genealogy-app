import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.routes.auth import router as auth_router
from app.api.routes.wechat import router as wechat_router
from app.db.session import Base, get_db
from app.models import User, Family, NotificationRecord
from app.models.wechat import WechatDevice, WechatDelivery
from app.core.legal import CURRENT_TERMS_VERSION
from app.core.security import hash_password
from app.services import wechat_push as push
from app.services.accounts import revoke_device_subscriptions, delete_user_data

class WechatPushTest(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory=sessionmaker(bind=self.engine,expire_on_commit=False)
        self.env=patch.dict(os.environ,{'WECHAT_APP_ID':'test-app','WECHAT_APP_SECRET':'test-secret','WECHAT_REMINDER_TEMPLATE_ID':'test-template','WECHAT_REMINDER_FIELDS':'{"thing1":"title","date2":"date","thing3":"family"}'})
        self.env.start();push._CACHE.clear()
        api=FastAPI();api.include_router(auth_router,prefix='/api');api.include_router(wechat_router,prefix='/api')
        def database():
            with self.factory() as db: yield db
        api.dependency_overrides[get_db]=database;self.client=TestClient(api)
        with self.factory() as db:
            db.add(User(id=1,username='test',password_hash=hash_password('password1'),notifications_enabled=True,system_notifications_enabled=True))
            db.add(Family(id=1,owner_id=1,name='测试族谱',avatar=''));db.commit()
        login=self.client.post('/api/auth/login',json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username':'test','password':'password1'})
        self.assertEqual(login.status_code,200)
        self.headers={'Authorization':'Bearer '+login.json()['access_token']}
    def tearDown(self):
        self.client.close();self.env.stop();self.engine.dispose()
    def register(self):
        response=Mock();response.json.return_value={'openid':'test-openid'}
        with patch.object(push.requests,'get',return_value=response) as get:
            result=self.client.post('/api/notifications/wechat-devices',headers=self.headers,json={'code':'one-time-test-code'})
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(get.call_args.kwargs['params']['js_code'],'one-time-test-code')
        return result.json()['id']
    def notice(self,db):
        record=NotificationRecord(user_id=1,family_id=1,title='生日测试',body='明日生日',due_date='2026-10-10',channel='in_app',status='SENT',dedupe_key='wechat-test',created_at=datetime.utcnow())
        db.add(record);db.commit();return record
    def test_register_exchange_once_and_revoke_session_device(self):
        device_id=self.register()
        with self.factory() as db:
            device=db.get(WechatDevice,device_id)
            self.assertEqual(device.allowance,1);self.assertTrue(device.session_id)
            revoke_device_subscriptions(db,1,device.session_id);db.commit()
            self.assertIsNone(db.get(WechatDevice,device_id))
    def test_real_message_payload_consumes_permission_and_records_accepted_once(self):
        self.register()
        token=Mock();token.json.return_value={'access_token':'test-access-token','expires_in':7200}
        sent=Mock();sent.json.return_value={'errcode':0}
        with self.factory() as db, patch.object(push.requests,'get',return_value=token), patch.object(push.requests,'post',return_value=sent) as post:
            self.notice(db)
            self.assertEqual(push.deliver(db),1);self.assertEqual(push.deliver(db),0);post.assert_called_once()
            payload=post.call_args.kwargs['json']
            self.assertEqual(payload['template_id'],'test-template');self.assertEqual(payload['touser'],'test-openid')
            self.assertEqual(payload['data']['date2']['value'],'2026-10-10')
            self.assertEqual(db.scalar(select(WechatDevice)).allowance,0)
            self.assertEqual(db.scalar(select(WechatDelivery)).status,'ACCEPTED')
    def test_provider_failure_never_claims_received_and_account_cleanup_is_complete(self):
        self.register()
        token=Mock();token.json.return_value={'access_token':'test-token'}
        rejected=Mock();rejected.json.return_value={'errcode':43101,'errmsg':'no permission'}
        with self.factory() as db, patch.object(push.requests,'get',return_value=token), patch.object(push.requests,'post',return_value=rejected):
            self.notice(db);self.assertEqual(push.deliver(db),0)
            self.assertEqual(db.scalar(select(WechatDelivery)).status,'FAILED')
            delete_user_data(db,db.get(User,1))
            self.assertIsNone(db.scalar(select(WechatDevice)));self.assertIsNone(db.scalar(select(WechatDelivery)))
    def test_unconfigured_never_calls_wechat_or_claims_enabled(self):
        with patch.dict(os.environ,{'WECHAT_APP_SECRET':''}), patch.object(push.requests,'get') as get:
            result=self.client.post('/api/notifications/wechat-devices',headers=self.headers,json={'code':'test'})
            self.assertEqual(result.status_code,503)
            with self.factory() as db:
                self.notice(db);self.assertEqual(push.deliver(db),0)
                self.assertFalse(push.status(db,db.get(User,1))['configured'])
            get.assert_not_called()

    def test_unregistered_and_retry_cooldown_records_do_not_fill_batch(self):
        self.register()
        now = datetime.utcnow()
        with self.factory() as db:
            db.add(User(id=2,username='no-device',password_hash='unused',notifications_enabled=True,system_notifications_enabled=True))
            for i in range(210):
                db.add(NotificationRecord(user_id=2,title='无设备旧提醒',body='test',channel='in_app',status='SENT',dedupe_key=f'none-{i}',created_at=now))
            for i in range(210):
                record=NotificationRecord(user_id=1,title='刚失败旧提醒',body='test',channel='in_app',status='SENT',dedupe_key=f'retry-{i}',created_at=now)
                db.add(record);db.flush()
                db.add(WechatDelivery(notification_id=record.id,user_id=1,status='FAILED',attempted_at=now))
            target=self.notice(db)
            with patch.object(push,'send',return_value={'errcode':0}) as sender:
                self.assertEqual(push.deliver(db,now),1)
                sender.assert_called_once()
                self.assertEqual(sender.call_args.args[1].id,target.id)
            self.assertEqual(db.scalar(select(WechatDelivery).where(WechatDelivery.notification_id==target.id)).status,'ACCEPTED')

    def test_interrupted_request_becomes_unknown_without_spending_another_authorization(self):
        self.register()
        now=datetime.utcnow()
        with self.factory() as db:
            target=self.notice(db)
            db.add(WechatDelivery(notification_id=target.id,user_id=1,status='SENDING',attempted_at=now-timedelta(minutes=6)))
            db.commit()
            with patch.object(push,'send') as sender:
                self.assertEqual(push.deliver(db,now),0)
                sender.assert_not_called()
            self.assertEqual(db.scalar(select(WechatDelivery)).status,'UNKNOWN')
            self.assertEqual(db.scalar(select(WechatDevice)).allowance,1)

    def test_ambiguous_response_or_timeout_never_claims_accepted_or_retries_automatically(self):
        for failure in ('empty', 'timeout'):
            with self.subTest(failure=failure):
                self.register()
                with self.factory() as db:
                    db.query(WechatDelivery).delete();db.query(NotificationRecord).delete();db.commit()
                    self.notice(db)
                    token=Mock();token.json.return_value={'access_token':'test-token'}
                    response=Mock();response.json.return_value={}
                    with patch.object(push.requests,'get',return_value=token), patch.object(push.requests,'post',return_value=response,side_effect=push.requests.Timeout() if failure=='timeout' else None) as sender:
                        self.assertEqual(push.deliver(db),0)
                        self.assertEqual(db.scalar(select(WechatDelivery)).status,'UNKNOWN')
                        allowance=db.scalar(select(WechatDevice)).allowance
                        self.assertEqual(push.deliver(db,datetime.utcnow()+timedelta(minutes=20)),0)
                        self.assertEqual(db.scalar(select(WechatDevice)).allowance,allowance)
                        sender.assert_called_once()

    def test_device_reassigned_before_authorization_reservation_is_not_used(self):
        self.register()
        with self.factory() as db:
            db.add(User(id=2,username='new-owner',password_hash='unused'));db.commit()
            self.notice(db)
            execute=db.execute
            changed=False
            def reassign(statement,*args,**kwargs):
                nonlocal changed
                if getattr(getattr(statement,'table',None),'name',None)=='wechat_devices' and not changed:
                    changed=True
                    execute(update(WechatDevice).values(user_id=2))
                return execute(statement,*args,**kwargs)
            with patch.object(db,'execute',side_effect=reassign), patch.object(push,'send') as sender:
                self.assertEqual(push.deliver(db),0)
                sender.assert_not_called()
            self.assertTrue(changed)
            self.assertEqual(db.scalar(select(WechatDevice)).allowance,1)
            self.assertEqual(db.scalar(select(WechatDelivery)).status,'PENDING')

    def test_lost_family_access_cancels_without_spending_authorization(self):
        self.register()
        with self.factory() as db:
            db.add(User(id=2,username='other-owner',password_hash='unused'))
            db.get(Family,1).owner_id=2;db.commit()
            self.notice(db)
            with patch.object(push,'send') as sender:
                self.assertEqual(push.deliver(db),0)
                sender.assert_not_called()
            self.assertEqual(db.scalar(select(WechatDevice)).allowance,1)
            self.assertEqual(db.scalar(select(WechatDelivery)).status,'CANCELLED')

    def test_stale_worker_cannot_claim_after_another_attempt_changes_timestamp(self):
        self.register()
        now=datetime.utcnow()
        with self.factory() as db:
            notice=self.notice(db)
            db.add(WechatDelivery(notification_id=notice.id,user_id=1,status='FAILED',attempted_at=now-timedelta(minutes=20)))
            db.commit()
            execute=db.execute
            changed=False
            def other_attempt(statement,*args,**kwargs):
                nonlocal changed
                values=getattr(statement,'_values',{}) or {}
                new_status=next((getattr(value,'value',None) for key,value in values.items() if getattr(key,'key',str(key))=='status'),None)
                if getattr(getattr(statement,'table',None),'name',None)=='wechat_deliveries' and new_status=='SENDING' and not changed:
                    changed=True
                    execute(update(WechatDelivery).values(attempted_at=now))
                return execute(statement,*args,**kwargs)
            with patch.object(db,'execute',side_effect=other_attempt), patch.object(push,'send') as sender:
                self.assertEqual(push.deliver(db,now),0)
                sender.assert_not_called()
            self.assertTrue(changed)
            self.assertEqual(db.scalar(select(WechatDevice)).allowance,1)

    def test_concurrent_delivery_creation_does_not_abort_batch_or_duplicate_send(self):
        self.register()
        with self.factory() as db:
            notice=self.notice(db)
            nested=db.begin_nested
            competed=False
            def create_first():
                nonlocal competed
                if not competed:
                    competed=True
                    db.add(WechatDelivery(notification_id=notice.id,user_id=1,status='ACCEPTED'))
                    db.commit()
                return nested()
            with patch.object(db,'begin_nested',side_effect=create_first), patch.object(push,'send') as sender:
                self.assertEqual(push.deliver(db),0)
                sender.assert_not_called()
            self.assertTrue(competed)
            self.assertEqual(db.scalar(select(WechatDevice)).allowance,1)
            self.assertEqual(db.scalar(select(WechatDelivery)).status,'ACCEPTED')
if __name__=='__main__': unittest.main()
