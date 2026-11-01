"""真实会话、账户清理、私有图片和通知投递，全部使用隔离数据库与临时文件。"""
import base64
from datetime import date, datetime, timedelta
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import router as auth_router
from app.api.routes.assets import router as assets_router
from app.api.routes.notifications import router as notifications_router
from app.core.config import settings
from app.core.legal import CURRENT_TERMS_VERSION
from app.core.security import _encode, hash_password
from app.db.session import Base, get_db
from app.models import (AuditLog, Family, FamilyMember, FamilyMembership, FamilyRelationship,
                        FileAsset, Invitation, LoginLog, NotificationRecord, Reminder,
                        SmsVerificationRecord, User, UserSession)
from app.services import notifications
from app.services.assets import asset_path


class AccountServicesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:',
            connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ASSET_STORAGE_DIR': self.directory.name,
            'WEB_PUSH_VAPID_PUBLIC_KEY': '', 'WEB_PUSH_VAPID_PRIVATE_KEY': '', 'WEB_PUSH_VAPID_SUBJECT': '',
            'UNIPUSH_APP_ID': '', 'UNIPUSH_APP_KEY': '', 'UNIPUSH_MASTER_SECRET': '',
            'NOTIFICATION_SCHEDULER_ENABLED': 'true'})
        self.env.start()
        api = FastAPI()
        for router in (auth_router, assets_router, notifications_router):
            api.include_router(router, prefix='/api')
        def isolated_db():
            with self.factory() as db:
                yield db
        api.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(api)
        key = ec.generate_private_key(ec.SECP256R1())
        self.push_config = {'WEB_PUSH_VAPID_PUBLIC_KEY': base64.urlsafe_b64encode(key.public_key().public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint)).decode().rstrip('='),
            'WEB_PUSH_VAPID_PRIVATE_KEY': base64.urlsafe_b64encode(key.private_numbers().private_value.to_bytes(32, 'big')).decode().rstrip('='),
            'WEB_PUSH_VAPID_SUBJECT': 'mailto:test@example.com'}
        self.user_id = self.add_user('owner')
        self.other_id = self.add_user('other')
        self.headers = self.login('owner')
        self.other_headers = self.login('other')

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.directory.cleanup()
        self.engine.dispose()

    def add_user(self, username, **kwargs):
        with self.factory() as db:
            user = User(username=username, password_hash=hash_password('password1'), **kwargs)
            db.add(user)
            db.commit()
            return user.id

    def login(self, username):
        response = self.client.post('/api/auth/login', json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': username, 'password': 'password1'})
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    def legacy_token(self, user_id, username, issued_at=None):
        header = _encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
        payload = {'sub': str(user_id), 'username': username, 'exp': int(time.time()) + 3600}
        if issued_at is not None:
            payload['iat'] = issued_at
        body = _encode(json.dumps(payload).encode())
        signature = _encode(hmac.new(settings.secret_key.encode(), f'{header}.{body}'.encode(), hashlib.sha256).digest())
        return f'{header}.{body}.{signature}'

    def add_family(self, owner_id=None, name='测试家族'):
        owner_id = owner_id or self.user_id
        with self.factory() as db:
            family = Family(owner_id=owner_id, name=name)
            db.add(family)
            db.flush()
            db.get(User, owner_id).active_family_id = family.id
            db.commit()
            return family.id

    def image_payload(self):
        stream = io.BytesIO()
        Image.new('RGB', (4, 4), 'red').save(stream, format='PNG')
        self.image_bytes = stream.getvalue()
        return {'filename': '../../avatar.png', 'content_type': 'image/png',
                'data_base64': base64.b64encode(self.image_bytes).decode()}

    def test_login_sessions_are_unique_revocable_and_isolated(self):
        second = self.login('owner')
        self.assertNotEqual(second, self.headers)
        listed = self.client.get('/api/auth/sessions', headers=self.headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(len(listed.json()), 2)
        current = next(item['id'] for item in listed.json() if item['current'])
        other_session = self.client.get('/api/auth/sessions', headers=self.other_headers).json()[0]['id']
        denied = self.client.delete(f'/api/auth/sessions/{other_session}', headers=self.headers)
        self.assertEqual(denied.status_code, 404)
        revoked = self.client.delete(f'/api/auth/sessions/{current}', headers=second)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers=second).status_code, 200)
        logout = self.client.post('/api/auth/logout', headers=second)
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers=second).status_code, 401)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == self.user_id)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'session_logout')), 1)

    def test_legacy_session_registers_once_and_revocation_is_permanent(self):
        headers = {'Authorization': 'Bearer ' + self.legacy_token(self.user_id, 'owner')}
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 401)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == self.user_id)), 2)

    def test_legacy_reset_cutoff_rejects_same_second_without_registering_session(self):
        cutoff = int(time.time()) - 2
        with self.factory() as db:
            db.get(User, self.user_id).sessions_valid_after = datetime.utcfromtimestamp(cutoff) + timedelta(microseconds=750000)
            baseline = db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == self.user_id))
            db.commit()
        for issued_at in (None, cutoff - 1, cutoff):
            with self.subTest(issued_at=issued_at):
                headers = {'Authorization': 'Bearer ' + self.legacy_token(self.user_id, 'owner', issued_at)}
                self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 401)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == self.user_id)), baseline)
        later = {'Authorization': 'Bearer ' + self.legacy_token(self.user_id, 'owner', cutoff + 1)}
        self.assertEqual(self.client.get('/api/auth/me', headers=later).status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout', headers=later).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers=later).status_code, 401)

    def test_registered_modern_session_can_login_in_reset_second_but_still_revoke(self):
        cutoff = int(time.time()) - 2
        with self.factory() as db:
            db.get(User, self.user_id).sessions_valid_after = datetime.utcfromtimestamp(cutoff) + timedelta(microseconds=750000)
            db.commit()
        with patch('app.core.security.time.time', return_value=cutoff):
            same_second = self.login('owner')
        self.assertEqual(self.client.get('/api/auth/me', headers=same_second).status_code, 200)
        with patch('app.core.security.time.time', return_value=cutoff - 1):
            before_reset = self.login('owner')
        self.assertEqual(self.client.get('/api/auth/me', headers=before_reset).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/logout', headers=same_second).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers=same_second).status_code, 401)

    def test_preferences_persist_and_validate_input(self):
        response = self.client.patch('/api/auth/preferences', headers=self.headers,
            json={'notifications_enabled': False, 'system_notifications_enabled': True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.client.get('/api/auth/me', headers=self.headers).json()['notifications_enabled'])
        with self.factory() as db:
            self.assertTrue(db.get(User, self.user_id).privacy_updated_at)
            self.assertTrue(db.scalar(select(AuditLog).where(AuditLog.action == 'preferences_updated')))
        for payload in ({}, {'notifications_enabled': None}, {'unknown': False}):
            self.assertEqual(self.client.patch('/api/auth/preferences', headers=self.headers, json=payload).status_code, 422)

    def test_password_reset_revokes_active_and_unregistered_legacy_sessions(self):
        with self.factory() as db:
            db.get(User, self.user_id).phone = '13800138000'
            db.add(SmsVerificationRecord(phone='13800138000', scene='reset_password', status='VERIFIED',
                sent_at=datetime.utcnow(), verified_at=datetime.utcnow()))
            db.commit()
        legacy = {'Authorization': 'Bearer ' + self.legacy_token(self.user_id, 'owner')}
        with patch('app.api.routes.auth.check_sms_code', return_value=True):
            response = self.client.post('/api/auth/forgot-password', json={
                'phone': '13800138000', 'sms_code': '123456', 'new_password': 'newpassword1'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/auth/me', headers=self.headers).status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers=legacy).status_code, 401)
        new = self.client.post('/api/auth/login', json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'owner', 'password': 'newpassword1'})
        self.assertEqual(new.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + new.json()['access_token']}).status_code, 200)

    def test_change_phone_consumes_new_proof_and_clears_old_phone_records(self):
        with self.factory() as db:
            db.get(User, self.user_id).phone = '13800138000'
            db.add(SmsVerificationRecord(phone='13800138000', scene='login'))
            db.add(SmsVerificationRecord(phone='13900139000', scene='modify_phone', status='VERIFIED',
                sent_at=datetime.utcnow(), verified_at=datetime.utcnow()))
            db.commit()
        with patch('app.api.routes.auth.check_sms_code', return_value=True):
            response = self.client.post('/api/auth/bind-phone', headers=self.headers,
                json={'phone': '13900139000', 'sms_code': '123456', 'scene': 'modify_phone'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['phone'], '13900139000')
        with self.factory() as db:
            self.assertFalse(db.scalar(select(SmsVerificationRecord).where(SmsVerificationRecord.phone == '13800138000')))
            self.assertEqual(db.scalar(select(SmsVerificationRecord).where(SmsVerificationRecord.phone == '13900139000')).status, 'CONSUMED')

    def test_malformed_access_tokens_return_401(self):
        for value in ('invalid', '___invalid__.a.b', 'x' * 5000, 'a.b.c'):
            with self.subTest(value=value[:15]):
                self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + value}).status_code, 401)

    def test_images_persist_and_have_family_authorization(self):
        family_id = self.add_family()
        third = self.add_user('third')
        third_headers = self.login('third')
        with self.factory() as db:
            db.add(FamilyMembership(family_id=family_id, user_id=self.other_id, role='VIEWER'))
            db.commit()
        response = self.client.post('/api/assets', headers=self.headers, json=self.image_payload())
        self.assertEqual(response.status_code, 201, response.text)
        asset_id = response.json()['id']
        url = response.json()['url']
        self.assertEqual(asset_path(asset_id).read_bytes(), self.image_bytes)
        self.assertEqual(self.client.get(url, headers=self.headers).content, self.image_bytes)
        self.assertEqual(self.client.get(url, headers=self.other_headers).status_code, 200)
        self.assertEqual(self.client.get(url, headers=third_headers).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 401)
        query = self.client.get(url, params={'token': self.headers['Authorization'][7:]})
        self.assertEqual(query.status_code, 401)
        self.assertEqual(self.client.get(url, headers=self.headers).headers['cache-control'], 'private, no-store')
        with self.factory() as db:
            asset = db.get(FileAsset, asset_id)
            self.assertEqual(asset.filename, 'avatar.png')
            self.assertEqual(asset.storage_path, f'{asset_id}.bin')
            self.assertEqual(asset.size_bytes, len(self.image_bytes))
            self.assertEqual(asset.sha256, hashlib.sha256(self.image_bytes).hexdigest())
            family = db.get(Family, family_id)
            family.avatar = url
            db.commit()
        self.assertEqual(self.client.delete(f'/api/assets/{asset_id}', headers=self.other_headers).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/assets/{asset_id}', headers=self.headers).status_code, 200)
        self.assertFalse(asset_path(asset_id).exists())
        with self.factory() as db:
            self.assertEqual(db.get(Family, family_id).avatar, '')
            self.assertEqual(db.get(Family, family_id).revision, 1)

    def test_upload_explicit_family_ignores_other_device_active_context(self):
        owned = self.add_family()
        shared = self.add_family(self.other_id, '共享家族')
        with self.factory() as db:
            db.add(FamilyMembership(family_id=shared, user_id=self.user_id, role='EDITOR'))
            db.get(User, self.user_id).active_family_id = shared
            db.commit()
        response = self.client.post('/api/assets', headers=self.headers, json={**self.image_payload(), 'family_id': owned})
        self.assertEqual(response.status_code, 201, response.text)
        with self.factory() as db:
            self.assertEqual(db.get(FileAsset, response.json()['id']).family_id, owned)
        denied = self.client.post('/api/assets', headers=self.other_headers, json={**self.image_payload(), 'family_id': owned})
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(self.client.post('/api/assets', headers=self.headers,
            json={**self.image_payload(), 'family_id': 9999}).status_code, 404)

    def test_images_reject_malformed_large_and_viewer_uploads(self):
        payload = self.image_payload()
        for bad in ({**payload, 'data_base64': 'bad!'},
                    {**payload, 'content_type': 'image/jpeg'},
                    {**payload, 'data_base64': base64.b64encode(b'<svg></svg>').decode()},
                    {**payload, 'data_base64': base64.b64encode(b'x' * (2*1024*1024+1)).decode()}):
            response = self.client.post('/api/assets', headers=self.headers, json=bad)
            self.assertIn(response.status_code, (413, 422), response.text)
        family_id = self.add_family()
        with self.factory() as db:
            db.add(FamilyMembership(family_id=family_id, user_id=self.other_id, role='VIEWER'))
            db.get(User, self.other_id).active_family_id = family_id
            db.commit()
        self.assertEqual(self.client.post('/api/assets', headers=self.other_headers, json=payload).status_code, 403)

    def test_delete_account_cleans_owned_and_shared_records_and_files(self):
        owned = self.add_family()
        shared = self.add_family(self.other_id, '另一家族')
        image = self.client.post('/api/assets', headers=self.headers, json=self.image_payload()).json()
        with self.factory() as db:
            db.get(User, self.user_id).phone = '13800138000'
            db.get(User, self.other_id).active_family_id = owned
            db.get(Family, shared).avatar = image['url']
            db.add(FamilyMembership(family_id=shared, user_id=self.user_id, role='EDITOR'))
            db.add(FamilyMembership(family_id=owned, user_id=self.other_id, role='EDITOR'))
            member = FamilyMember(family_id=owned, client_id='a', name='成员')
            reminder = Reminder(family_id=owned, client_id='r', title='提醒', date='2026-10-10')
            db.add_all([member, reminder]); db.flush()
            from app.models.user import PushSubscription, MobilePushDevice
            db.add_all([
                PushSubscription(user_id=self.user_id, endpoint='https://fcm.googleapis.com/fcm/send/deleted',
                    endpoint_hash='1'*64, p256dh='unused', auth='unused'),
                MobilePushDevice(user_id=self.user_id, client_id='deleted-client', client_hash='2'*64, platform='android'),
                FamilyRelationship(family_id=owned, from_member_id=member.id, to_member_id=member.id, kind='parent'),
                Invitation(family_id=shared, inviter_id=self.other_id, invitee='owner', invitee_user_id=self.user_id),
                NotificationRecord(user_id=self.other_id, family_id=owned, reminder_id=reminder.id,
                    channel='in_app', status='SENT'),
                NotificationRecord(user_id=self.user_id, family_id=shared, channel='in_app', status='SENT'),
                SmsVerificationRecord(phone='13800138000', scene='bind_phone'),
                AuditLog(user_id=self.user_id, family_id=shared, action='member_updated'),
            ]); db.commit()
        response = self.client.delete('/api/auth/me', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/auth/me', headers=self.headers).status_code, 401)
        self.assertFalse(asset_path(image['id']).exists())
        with self.factory() as db:
            self.assertIsNone(db.get(User, self.user_id))
            self.assertIsNone(db.get(Family, owned))
            self.assertTrue(db.get(Family, shared))
            self.assertEqual(db.get(Family, shared).avatar, '')
            self.assertIsNone(db.get(User, self.other_id).active_family_id)
            for model in (FamilyMember, FamilyRelationship, Reminder, Invitation,
                          FamilyMembership, FileAsset, NotificationRecord, SmsVerificationRecord, PushSubscription, MobilePushDevice):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 0, model.__name__)
            self.assertEqual(db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == self.user_id)), 0)
            self.assertFalse(db.scalar(select(AuditLog).where(AuditLog.user_id == self.user_id)))

    def test_notifications_generate_without_ui_and_deduplicate_with_preferences(self):
        family = self.add_family()
        with self.factory() as db:
            db.add(FamilyMembership(family_id=family, user_id=self.other_id, role='VIEWER'))
            reminder = Reminder(family_id=family, client_id='r', title='生日', date='1992-10-13', advance='提前3天', repeat='每年')
            db.add(reminder); db.commit()
            now = datetime(2026, 10, 10, 10)
            self.assertEqual(notifications.generate_notifications(db, now), 2)
            self.assertEqual(notifications.generate_notifications(db, now), 0)
            # 同一天重启不会重复；纪念日当天仍提醒一次。
            self.assertEqual(notifications.generate_notifications(db, datetime(2026, 10, 13, 10)), 2)
            db.get(User, self.other_id).notifications_enabled = False
            db.commit()
            self.assertEqual(notifications.generate_notifications(db, datetime(2027, 10, 10, 10)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(NotificationRecord)), 5)
        inbox = self.client.get('/api/notifications', headers=self.headers)
        self.assertEqual(inbox.status_code, 200, inbox.text)
        self.assertEqual(len(inbox.json()), 3)
        record = inbox.json()[0]['id']
        self.assertEqual(self.client.patch(f'/api/notifications/{record}/read', headers=self.other_headers).status_code, 404)
        first = self.client.patch(f'/api/notifications/{record}/read', headers=self.headers)
        second = self.client.patch(f'/api/notifications/{record}/read', headers=self.headers)
        self.assertEqual(first.json()['read_at'], second.json()['read_at'])
        self.assertEqual(self.client.post('/api/notifications/read-all', headers=self.headers).json()['count'], 2)
        self.assertTrue(all(item['read_at'] for item in self.client.get('/api/notifications', headers=self.headers).json()))
        self.assertTrue(all(item['read_at'] is None for item in self.client.get('/api/notifications', headers=self.other_headers).json()))

    def test_api_lifespan_starts_real_scheduler_in_isolated_database(self):
        import threading
        import importlib
        main = importlib.import_module('app.main')
        family = self.add_family()
        with self.factory() as db:
            db.add(Reminder(family_id=family, client_id='scheduled', title='后台任务提醒',
                date=datetime.now(notifications.CHINA).date().isoformat(), repeat='仅一次'))
            db.commit()
        completed = threading.Event()
        actual_tick = notifications.notification_tick
        def observed_tick():
            actual_tick()
            completed.set()
        with patch.object(main, 'engine', self.engine), patch.object(main, 'ensure_database'), patch.object(main, 'ensure_schema'), \
             patch.object(notifications, 'SessionLocal', self.factory), patch.object(notifications, 'notification_tick', observed_tick):
            with TestClient(main.app) as running_api:
                self.assertTrue(completed.wait(5), 'API 启动后后台任务没有完成')
                self.assertEqual(running_api.get('/health').status_code, 200)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(NotificationRecord)), 1)

    def test_solar_lunar_qingming_and_timezone_occurrences(self):
        solar = Reminder(date='2000-02-29', repeat='每年', calendar='solar')
        self.assertEqual(notifications.reminder_occurrences(solar, date(2026, 2, 28)), [])
        self.assertIn(date(2028, 2, 29), notifications.reminder_occurrences(solar, date(2028, 2, 29)))
        lunar = Reminder(date='2024-02-10', repeat='每年', calendar='lunar', lunar_month=1, lunar_day=1, lunar_leap=False)
        self.assertIn(date(2026, 2, 17), notifications.reminder_occurrences(lunar, date(2026, 2, 17)))
        leap = Reminder(date='2023-03-22', repeat='每年', calendar='lunar', lunar_month=2, lunar_day=1, lunar_leap=True)
        self.assertEqual(notifications.reminder_occurrences(leap, date(2026, 3, 22)), [])
        qingming = Reminder(date='2024-04-04', repeat='每年', calendar='qingming')
        self.assertIn(date(2026, 4, 5), notifications.reminder_occurrences(qingming, date(2026, 4, 5)))
        once = Reminder(date='2025-10-10', repeat='仅一次', calendar='solar')
        self.assertEqual(notifications.reminder_occurrences(once, date(2026, 10, 10)), [date(2025, 10, 10)])
        family = self.add_family()
        with self.factory() as db:
            db.add(Reminder(family_id=family, client_id='tz', title='时区提醒', date='2026-10-10', repeat='仅一次'))
            db.commit()
            from datetime import timezone
            self.assertEqual(notifications.generate_notifications(db, datetime(2026, 10, 9, 16, 0, tzinfo=timezone.utc)), 1)

    def test_unconfigured_push_has_truthful_status_and_never_sends(self):
        status = self.client.get('/api/notifications/delivery-status', headers=self.headers)
        self.assertEqual(status.status_code, 200, status.text)
        self.assertTrue(status.json()['in_app']['configured'])
        self.assertFalse(status.json()['web_push']['configured'])
        self.assertFalse(status.json()['mobile_push']['configured'])
        with self.factory() as db, patch.object(notifications, 'send_web_push') as sender:
            self.assertEqual(notifications.deliver_pending_push(db), 0)
            sender.assert_not_called()

    def subscription_payload(self):
        device_key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        return {'endpoint': 'https://fcm.googleapis.com/fcm/send/test-device',
                'keys': {'p256dh': base64.urlsafe_b64encode(device_key).decode().rstrip('='),
                         'auth': base64.urlsafe_b64encode(b'b'*16).decode().rstrip('=')}}

    def test_web_push_subscription_and_delivery_is_actual_once_and_private(self):
        from app.models.user import PushSubscription
        configured = self.push_config
        with patch.dict(os.environ, configured):
            for endpoint in ('https://127.0.0.1/push', 'http://fcm.googleapis.com/push', 'https://fcm.googleapis.com.evil.example/push'):
                payload = {**self.subscription_payload(), 'endpoint': endpoint}
                self.assertEqual(self.client.post('/api/notifications/subscriptions', headers=self.headers, json=payload).status_code, 422)
            subscription = self.client.post('/api/notifications/subscriptions', headers=self.headers, json=self.subscription_payload())
            self.assertEqual(subscription.status_code, 201, subscription.text)
            subscription_id = subscription.json()['id']
            self.assertEqual(self.client.delete(f'/api/notifications/subscriptions/{subscription_id}', headers=self.other_headers).status_code, 404)
            with self.factory() as db:
                db.get(User, self.user_id).system_notifications_enabled = True
                record = NotificationRecord(user_id=self.user_id, title='投递测试', body='正文', channel='in_app',
                    status='SENT', created_at=datetime.utcnow(), push_status='PENDING')
                db.add(record); db.commit()
                with patch.object(notifications, 'send_web_push') as sender:
                    self.assertEqual(notifications.deliver_pending_push(db), 1)
                    self.assertEqual(notifications.deliver_pending_push(db), 0)
                    sender.assert_called_once()
                self.assertEqual(db.get(NotificationRecord, record.id).push_status, 'SENT')
            # 同一设备改登其他账号后，服务端订阅归属随登记更新。
            moved = self.client.post('/api/notifications/subscriptions', headers=self.other_headers, json=self.subscription_payload())
            self.assertEqual(moved.status_code, 201)
            with self.factory() as db:
                self.assertEqual(db.get(PushSubscription, subscription_id).user_id, self.other_id)
            self.assertEqual(self.client.delete(f'/api/notifications/subscriptions/{subscription_id}', headers=self.headers).status_code, 404)
            self.assertEqual(self.client.delete(f'/api/notifications/subscriptions/{subscription_id}', headers=self.other_headers).status_code, 200)

    def test_revoke_session_removes_only_its_push_devices(self):
        from app.models.user import PushSubscription, MobilePushDevice
        second = self.login('owner')
        listed = self.client.get('/api/auth/sessions', headers=self.headers).json()
        current = next(item['id'] for item in listed if item['current'])
        other = next(item['id'] for item in listed if not item['current'])
        with self.factory() as db:
            db.add_all([
                PushSubscription(user_id=self.user_id, session_id=current, endpoint='https://fcm.googleapis.com/fcm/send/current',
                    endpoint_hash='c'*64, p256dh='unused', auth='unused'),
                PushSubscription(user_id=self.user_id, session_id=other, endpoint='https://fcm.googleapis.com/fcm/send/other',
                    endpoint_hash='d'*64, p256dh='unused', auth='unused'),
                MobilePushDevice(user_id=self.user_id, session_id=current, client_id='current-client', client_hash='e'*64, platform='android'),
                MobilePushDevice(user_id=self.user_id, session_id=other, client_id='other-client', client_hash='f'*64, platform='ios'),
            ]); db.commit()
        self.assertEqual(self.client.delete(f'/api/auth/sessions/{current}', headers=second).status_code, 200)
        with self.factory() as db:
            self.assertEqual([item.session_id for item in db.scalars(select(PushSubscription))], [other])
            self.assertEqual([item.session_id for item in db.scalars(select(MobilePushDevice))], [other])
        self.assertEqual(self.client.post('/api/auth/logout', headers=second).status_code, 200)
        with self.factory() as db:
            self.assertFalse(list(db.scalars(select(PushSubscription))))
            self.assertFalse(list(db.scalars(select(MobilePushDevice))))

    def test_native_device_register_is_private_and_tracks_session(self):
        from app.models.user import MobilePushDevice
        payload = {'client_id': 'isolated-client-id', 'platform': 'android'}
        self.assertEqual(self.client.post('/api/notifications/mobile-devices', headers=self.headers, json=payload).status_code, 503)
        configured = {'UNIPUSH_APP_ID': 'app', 'UNIPUSH_APP_KEY': 'key', 'UNIPUSH_MASTER_SECRET': 'secret'}
        with patch.dict(os.environ, configured):
            result = self.client.post('/api/notifications/mobile-devices', headers=self.headers, json=payload)
            self.assertEqual(result.status_code, 201, result.text)
            device_id = result.json()['id']
            with self.factory() as db:
                device = db.get(MobilePushDevice, device_id)
                self.assertEqual(device.user_id, self.user_id)
                self.assertTrue(device.session_id)
            self.assertEqual(self.client.delete(f'/api/notifications/mobile-devices/{device_id}', headers=self.other_headers).status_code, 404)
            self.assertEqual(self.client.delete(f'/api/notifications/mobile-devices/{device_id}', headers=self.headers).status_code, 200)


if __name__ == '__main__':
    unittest.main()
