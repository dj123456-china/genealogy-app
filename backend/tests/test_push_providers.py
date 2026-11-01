"""真实 Web Push 加密/HTTP链路和 UniPush 2 协议，网络完全拦截。"""
import base64
from datetime import datetime, timedelta
import hashlib
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import Family, NotificationRecord, User, UserSession
from app.services.notifications import send_web_push, push_configuration, deliver_pending_push
from app.services.mobile_push import (send_mobile_push, mobile_configuration, deliver_pending_mobile,
                                     _TOKEN_CACHE)


def encoded(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def vapid_environment():
    key = ec.generate_private_key(ec.SECP256R1())
    return {'WEB_PUSH_VAPID_PUBLIC_KEY': encoded(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
            'WEB_PUSH_VAPID_PRIVATE_KEY': encoded(key.private_numbers().private_value.to_bytes(32, 'big')),
            'WEB_PUSH_VAPID_SUBJECT': 'mailto:test@example.com'}


class PushProtocolsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        _TOKEN_CACHE.clear()

    def tearDown(self):
        _TOKEN_CACHE.clear()
        self.engine.dispose()

    def session_for(self, db, user_id):
        session = UserSession(user_id=user_id, token_hash=hashlib.sha256(os.urandom(16)).hexdigest(), expires_at=datetime.utcnow()+timedelta(days=1))
        db.add(session);db.flush()
        return session.id

    def test_web_push_builds_encrypted_http_request_with_real_keys(self):
        receiver = ec.generate_private_key(ec.SECP256R1())
        subscription = SimpleNamespace(endpoint='https://fcm.googleapis.com/fcm/send/isolated',
            p256dh=encoded(receiver.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)), auth=encoded(os.urandom(16)))
        record = SimpleNamespace(id=1, title='隔离测试', body='秘密提醒正文')
        with patch.dict(os.environ, vapid_environment()), patch('pywebpush.requests.post') as network:
            network.return_value = SimpleNamespace(status_code=201, text='')
            configuration = push_configuration()
            self.assertTrue(configuration['configured'])
            send_web_push(subscription, record, configuration)
            network.assert_called_once()
            args, kwargs = network.call_args
            self.assertEqual(args[0], subscription.endpoint)
            self.assertEqual(kwargs['timeout'], 10)
            self.assertEqual(kwargs['headers']['content-encoding'], 'aes128gcm')
            self.assertTrue(kwargs['headers']['Authorization'].startswith('vapid '))
            self.assertIsInstance(kwargs['data'], bytes)
            self.assertNotIn(record.body.encode(), kwargs['data'])

    def test_invalid_vapid_configuration_is_reported_as_unconfigured(self):
        with patch.dict(os.environ, {'WEB_PUSH_VAPID_PUBLIC_KEY': 'bad', 'WEB_PUSH_VAPID_PRIVATE_KEY': 'bad',
                                    'WEB_PUSH_VAPID_SUBJECT': 'mailto:test@example.com'}):
            self.assertFalse(push_configuration()['configured'])
            self.assertTrue(push_configuration()['error'])
        with patch.dict(os.environ, {**vapid_environment(), 'WEB_PUSH_VAPID_PUBLIC_KEY': encoded(b'x' * 65)}):
            self.assertFalse(push_configuration()['configured'])

    def test_uni_push_signs_auth_and_submits_actual_notification(self):
        environment = {'UNIPUSH_APP_ID': 'test-app', 'UNIPUSH_APP_KEY': 'test-key', 'UNIPUSH_MASTER_SECRET': 'test-secret'}
        responses = [Mock(), Mock(), Mock()]
        responses[0].json.return_value = {'code': 0, 'data': {'token': 'isolated-provider-token', 'expire_time': int((__import__('time').time()+3600)*1000)}}
        responses[1].json.return_value = {'code': 0, 'data': {'task-1': {'isolated-cid': 'online'}}}
        responses[2].json.return_value = {'code': 0, 'data': {'task-2': {'isolated-cid': 'online'}}}
        device = SimpleNamespace(client_id='isolated-cid', platform='android')
        record = SimpleNamespace(id=23, title='标题', body='正文')
        with patch.dict(os.environ, environment), patch('app.services.mobile_push.requests.post', side_effect=responses) as network:
            configuration = mobile_configuration()
            self.assertTrue(configuration['configured'])
            self.assertEqual(send_mobile_push(device, record, configuration)['code'], 0)
            send_mobile_push(device, record, configuration)
            self.assertEqual(network.call_count, 3)  # 认证缓存：两次投递只认证一次。
            auth = network.call_args_list[0]
            auth_data = auth.kwargs['json']
            self.assertEqual(auth.args[0], 'https://restapi.getui.com/v2/test-app/auth')
            self.assertEqual(auth_data['sign'], hashlib.sha256(('test-key'+auth_data['timestamp']+'test-secret').encode()).hexdigest())
            push = network.call_args_list[1]
            self.assertEqual(push.args[0], 'https://restapi.getui.com/v2/test-app/push/single/cid')
            self.assertEqual(push.kwargs['headers'], {'token': 'isolated-provider-token'})
            self.assertEqual(push.kwargs['json']['audience']['cid'], ['isolated-cid'])
            self.assertEqual(push.kwargs['json']['push_message']['notification']['body'], '正文')
            self.assertEqual(push.kwargs['json']['request_id'], network.call_args_list[2].kwargs['json']['request_id'])

    def test_uni_push_refreshes_rejected_cached_token_once(self):
        environment = {'UNIPUSH_APP_ID': 'refresh-app', 'UNIPUSH_APP_KEY': 'key', 'UNIPUSH_MASTER_SECRET': 'secret'}
        bodies = [
            {'code': 0, 'data': {'token': 'old-token'}},
            {'code': 10001, 'msg': 'expired'},
            {'code': 0, 'data': {'token': 'new-token'}},
            {'code': 0, 'data': {'task': {'test-cid': 'online'}}},
        ]
        responses = []
        for body in bodies:
            response = Mock(); response.json.return_value = body; responses.append(response)
        with patch.dict(os.environ, environment), patch('app.services.mobile_push.requests.post', side_effect=responses) as network:
            result = send_mobile_push(SimpleNamespace(client_id='test-cid'), SimpleNamespace(id=1, title='title', body='body'), mobile_configuration())
            self.assertEqual(result['code'], 0)
            self.assertEqual(network.call_count, 4)
            self.assertEqual(network.call_args_list[1].kwargs['headers'], {'token': 'old-token'})
            self.assertEqual(network.call_args_list[3].kwargs['headers'], {'token': 'new-token'})

    def test_uni_push_does_not_claim_success_when_provider_rejects(self):
        with patch.dict(os.environ, {'UNIPUSH_APP_ID': 'test-app', 'UNIPUSH_APP_KEY': 'test-key', 'UNIPUSH_MASTER_SECRET': 'test-secret'}):
            response = Mock()
            response.json.return_value = {'code': 10001, 'msg': 'authentication failed'}
            with patch('app.services.mobile_push.requests.post', return_value=response):
                with self.assertRaisesRegex(RuntimeError, '10001'):
                    send_mobile_push(SimpleNamespace(client_id='isolated-cid'), SimpleNamespace(id=1, title='标题', body='正文'), mobile_configuration())

    def test_failed_web_push_is_recorded_and_expired_subscription_removed(self):
        from app.models.user import PushSubscription
        with self.factory() as db:
            user = User(username='push-test', password_hash='unused', notifications_enabled=True, system_notifications_enabled=True)
            db.add(user); db.flush()
            db.add(PushSubscription(user_id=user.id, session_id=self.session_for(db, user.id), endpoint='https://fcm.googleapis.com/fcm/send/test',
                endpoint_hash='a'*64, p256dh='unused', auth='unused'))
            record = NotificationRecord(user_id=user.id, title='test', body='body', channel='in_app',
                status='SENT', push_status='PENDING', created_at=datetime.utcnow())
            db.add(record); db.commit()
            error = RuntimeError('must not be logged with secret tokens')
            error.response = SimpleNamespace(status_code=410)
            with patch.dict(os.environ, vapid_environment()), patch('app.services.notifications.send_web_push', side_effect=error):
                self.assertEqual(deliver_pending_push(db), 0)
            self.assertEqual(record.push_status, 'FAILED')
            self.assertEqual(record.push_error, 'RuntimeError HTTP 410')
            self.assertFalse(list(db.scalars(select(PushSubscription))))

    def test_native_pending_push_is_accepted_once_and_failures_are_retryable(self):
        from app.models.user import MobilePushDevice
        with self.factory() as db:
            user = User(username='native-test', password_hash='unused', notifications_enabled=True, system_notifications_enabled=True)
            db.add(user); db.flush()
            db.add(MobilePushDevice(user_id=user.id, session_id=self.session_for(db, user.id), client_id='isolated-cid', client_hash='b'*64, platform='android'))
            record = NotificationRecord(user_id=user.id, title='test', body='body', channel='in_app',
                status='SENT', mobile_status='PENDING', created_at=datetime.utcnow())
            db.add(record); db.commit()
            env = {'UNIPUSH_APP_ID': 'test-app', 'UNIPUSH_APP_KEY': 'test-key', 'UNIPUSH_MASTER_SECRET': 'test-secret'}
            with patch.dict(os.environ, env), patch('app.services.mobile_push.send_mobile_push', return_value={'code': 0}) as sender:
                self.assertEqual(deliver_pending_mobile(db), 1)
                self.assertEqual(deliver_pending_mobile(db), 0)
                sender.assert_called_once()
            self.assertEqual(record.mobile_status, 'ACCEPTED')
            record.mobile_status = 'PENDING'; db.commit()
            with patch.dict(os.environ, env), patch('app.services.mobile_push.send_mobile_push', side_effect=TimeoutError('private endpoint')) as sender:
                self.assertEqual(deliver_pending_mobile(db), 0)
                self.assertEqual(deliver_pending_mobile(db), 0)
                sender.assert_called_once()
            self.assertEqual(record.mobile_status, 'FAILED')
            self.assertEqual(record.mobile_error, 'TimeoutError')
            record.mobile_attempted_at = datetime.utcnow() - timedelta(minutes=20); db.commit()
            with patch.dict(os.environ, env), patch('app.services.mobile_push.send_mobile_push', return_value={'code': 0}):
                self.assertEqual(deliver_pending_mobile(db), 1)
            self.assertEqual(record.mobile_status, 'ACCEPTED')

    def test_unregistered_old_notifications_do_not_block_registered_users(self):
        from app.models.user import MobilePushDevice, PushSubscription
        with self.factory() as db:
            db.add_all([User(id=1, username='no-device', password_hash='unused', notifications_enabled=True, system_notifications_enabled=True),
                        User(id=2, username='has-device', password_hash='unused', notifications_enabled=True, system_notifications_enabled=True)])
            db.flush()
            for i in range(150):
                db.add(NotificationRecord(user_id=1, title='无设备旧提醒', body='test', channel='in_app', status='SENT',
                    push_status='NO_SUBSCRIPTION', mobile_status='NO_DEVICE', created_at=datetime.utcnow()))
            record = NotificationRecord(user_id=2, title='有设备新提醒', body='test', channel='in_app', status='SENT',
                push_status='PENDING', mobile_status='PENDING', created_at=datetime.utcnow())
            db.add(record)
            session_id=self.session_for(db, 2)
            db.add(PushSubscription(user_id=2, session_id=session_id, endpoint='https://fcm.googleapis.com/fcm/send/isolated', endpoint_hash='c'*64, p256dh='unused', auth='unused'))
            db.add(MobilePushDevice(user_id=2, session_id=session_id, client_id='isolated-cid', client_hash='d'*64, platform='android'))
            db.commit()
            with patch.dict(os.environ, vapid_environment()), patch('app.services.notifications.send_web_push') as sender:
                self.assertEqual(deliver_pending_push(db), 1)
                sender.assert_called_once()
                self.assertEqual(record.push_status, 'SENT')
            environment = {'UNIPUSH_APP_ID': 'test-app', 'UNIPUSH_APP_KEY': 'test-key', 'UNIPUSH_MASTER_SECRET': 'test-secret'}
            with patch.dict(os.environ, environment), patch('app.services.mobile_push.send_mobile_push', return_value={'code': 0}) as sender:
                self.assertEqual(deliver_pending_mobile(db), 1)
                sender.assert_called_once()
                self.assertEqual(record.mobile_status, 'ACCEPTED')

    def test_expired_or_revoked_device_sessions_do_not_receive_notifications(self):
        from app.models.user import MobilePushDevice, PushSubscription
        with self.factory() as db:
            db.add(User(id=1,username='expired-test',password_hash='unused',notifications_enabled=True,system_notifications_enabled=True))
            db.flush()
            session_id=self.session_for(db,1)
            session=db.get(UserSession,session_id)
            db.add(PushSubscription(user_id=1,session_id=session_id,endpoint='https://fcm.googleapis.com/fcm/send/expired',endpoint_hash='e'*64,p256dh='unused',auth='unused'))
            db.add(MobilePushDevice(user_id=1,session_id=session_id,client_id='expired-cid',client_hash='f'*64,platform='android'))
            db.add(NotificationRecord(user_id=1,title='test',body='test',channel='in_app',status='SENT',push_status='PENDING',mobile_status='PENDING',created_at=datetime.utcnow()))
            db.commit()
            env={**vapid_environment(),'UNIPUSH_APP_ID':'test-app','UNIPUSH_APP_KEY':'test-key','UNIPUSH_MASTER_SECRET':'test-secret'}
            with patch.dict(os.environ,env), patch('app.services.notifications.send_web_push') as web, patch('app.services.mobile_push.send_mobile_push') as mobile:
                for expired,revoked in [(True,False),(False,True)]:
                    session.expires_at=datetime.utcnow()+timedelta(days=-1 if expired else 1)
                    session.revoked_at=datetime.utcnow() if revoked else None
                    db.commit()
                    self.assertEqual(deliver_pending_push(db),0)
                    self.assertEqual(deliver_pending_mobile(db),0)
                web.assert_not_called();mobile.assert_not_called()

    def test_lost_family_access_cancels_pending_web_and_mobile_push(self):
        from app.models.user import MobilePushDevice, PushSubscription
        with self.factory() as db:
            db.add_all([User(id=1,username='removed-member',password_hash='unused',notifications_enabled=True,system_notifications_enabled=True),User(id=2,username='family-owner',password_hash='unused')])
            db.flush()
            family=Family(owner_id=2,name='private',avatar='');db.add(family);db.flush()
            session_id=self.session_for(db,1)
            db.add(PushSubscription(user_id=1,session_id=session_id,endpoint='https://fcm.googleapis.com/fcm/send/removed',endpoint_hash='1'*64,p256dh='unused',auth='unused'))
            db.add(MobilePushDevice(user_id=1,session_id=session_id,client_id='removed-cid',client_hash='2'*64,platform='android'))
            record=NotificationRecord(user_id=1,family_id=family.id,title='private',body='private',channel='in_app',status='SENT',push_status='PENDING',mobile_status='PENDING',created_at=datetime.utcnow())
            db.add(record);db.commit()
            env={**vapid_environment(),'UNIPUSH_APP_ID':'test-app','UNIPUSH_APP_KEY':'test-key','UNIPUSH_MASTER_SECRET':'test-secret'}
            with patch.dict(os.environ,env), patch('app.services.notifications.send_web_push') as web, patch('app.services.mobile_push.send_mobile_push') as mobile:
                self.assertEqual(deliver_pending_push(db),0)
                self.assertEqual(deliver_pending_mobile(db),0)
                web.assert_not_called();mobile.assert_not_called()
            self.assertEqual(record.push_status,'CANCELLED')
            self.assertEqual(record.mobile_status,'CANCELLED')


if __name__ == '__main__':
    unittest.main()
