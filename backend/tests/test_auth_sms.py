"""Authentication SMS flows against isolated SQLite and a fake provider."""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import router as auth_router
from app.core.legal import CURRENT_TERMS_VERSION
from app.core.security import create_access_token, create_registration_token, hash_password, verify_password, decode_access_token, token_fingerprint
from app.db.session import Base, get_db
from app.models import LoginLog, SmsVerificationRecord, User, UserSession
from app.services import sms


PHONE = '13800138000'
OTHER_PHONE = '13900139000'
CODE = '123456'


class FakeSmsClient:
    def __init__(self):
        self.send_calls = []
        self.check_calls = []

    def send_sms_verify_code(self, request):
        self.send_calls.append(request)
        return SimpleNamespace(body=SimpleNamespace(success=True, model=SimpleNamespace()))

    def check_sms_verify_code(self, request):
        self.check_calls.append(request)
        return SimpleNamespace(
            body=SimpleNamespace(success=True, model=SimpleNamespace(verify_result='PASS'))
        )


class AuthSmsRoutesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            'sqlite+pysqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.provider = FakeSmsClient()
        self.provider_patch = patch.object(sms, '_client', return_value=self.provider)
        self.provider_patch.start()

        app = FastAPI()
        app.include_router(auth_router, prefix='/api')

        def isolated_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.provider_patch.stop()
        self.engine.dispose()

    def send(self, scene, phone=PHONE):
        response = self.client.post('/api/auth/send-sms', json={'phone': phone, 'scene': scene})
        self.assertEqual(response.status_code, 200, response.text)

    def add_user(self, *, username='member', phone=PHONE, password='old-password'):
        with self.session_factory() as db:
            user = User(username=username, phone=phone, password_hash=hash_password(password))
            db.add(user)
            db.commit()
            return user.id

    def sms_record(self, phone=PHONE):
        with self.session_factory() as db:
            return db.scalar(
                select(SmsVerificationRecord)
                .where(SmsVerificationRecord.phone == phone)
                .order_by(SmsVerificationRecord.id.desc())
            )

    def test_phone_and_code_are_required_at_auth_boundaries(self):
        cases = (
            ('/api/auth/register', {'username': 'new', 'password': 'password1', 'sms_code': CODE}, 422),
            ('/api/auth/register', {'username': 'new', 'password': 'password1', 'phone': PHONE}, 400),
            ('/api/auth/login/sms', {'sms_code': CODE}, 422),
            ('/api/auth/login/sms', {'phone': PHONE}, 422),
            ('/api/auth/forgot-password', {'sms_code': CODE, 'new_password': 'password2'}, 422),
            ('/api/auth/forgot-password', {'phone': PHONE, 'new_password': 'password2'}, 422),
            ('/api/auth/send-sms', {'scene': 'register'}, 422),
        )
        for path, payload, status in cases:
            with self.subTest(path=path, payload=payload):
                if path in {'/api/auth/register', '/api/auth/login/sms'}:
                    payload = dict(payload, accepted_terms_version=CURRENT_TERMS_VERSION)
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(self.provider.check_calls, [])
        self.assertEqual(self.provider.send_calls, [])

    def test_sms_login_registration_token_registers_once(self):
        self.send('login')
        handoff = self.client.post('/api/auth/login/sms', json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'phone': PHONE, 'sms_code': CODE})
        self.assertEqual(handoff.status_code, 200, handoff.text)
        handoff_data = handoff.json()
        self.assertTrue(handoff_data['requires_registration'])
        self.assertIsNone(handoff_data['access_token'])
        token = handoff_data['registration_token']
        self.assertTrue(token)
        self.assertEqual(self.sms_record().status, 'VERIFIED')

        registered = self.client.post(
            '/api/auth/register',
            json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'new', 'password': 'password1', 'phone': PHONE, 'registration_token': token},
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        self.assertEqual(registered.json()['user']['phone'], PHONE)
        self.assertTrue(registered.json()['access_token'])
        self.assertEqual(self.sms_record().status, 'CONSUMED')
        self.assertEqual(len(self.provider.check_calls), 1)

        # Remove the user so the replay reaches proof validation instead of the
        # duplicate-phone guard; the already consumed proof still must fail.
        with self.session_factory() as db:
            db.delete(db.scalar(select(User).where(User.phone == PHONE)))
            db.commit()
        replay = self.client.post(
            '/api/auth/register',
            json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'another', 'password': 'password1', 'phone': PHONE, 'registration_token': token},
        )
        self.assertEqual(replay.status_code, 400, replay.text)
        self.assertEqual(self.sms_record().status, 'CONSUMED')

    def test_registration_token_rejects_wrong_phone_and_wrong_scene(self):
        self.send('login')
        handoff = self.client.post('/api/auth/login/sms', json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'phone': PHONE, 'sms_code': CODE})
        token = handoff.json()['registration_token']
        wrong_phone = self.client.post(
            '/api/auth/register',
            json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'new', 'password': 'password1', 'phone': OTHER_PHONE, 'registration_token': token},
        )
        self.assertEqual(wrong_phone.status_code, 400, wrong_phone.text)
        self.assertEqual(self.sms_record().status, 'VERIFIED')

        with self.session_factory() as db:
            reset_record = SmsVerificationRecord(
                phone=OTHER_PHONE,
                scene='reset_password',
                request_id='a' * 32,
                sent_at=datetime.utcnow(),
                verified_at=datetime.utcnow(),
                status='VERIFIED',
            )
            db.add(reset_record)
            db.commit()
            wrong_scene_token = create_registration_token(OTHER_PHONE, reset_record.id)
        wrong_scene = self.client.post(
            '/api/auth/register',
            json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'new', 'password': 'password1', 'phone': OTHER_PHONE,
                  'registration_token': wrong_scene_token},
        )
        self.assertEqual(wrong_scene.status_code, 400, wrong_scene.text)
        self.assertEqual(self.sms_record(OTHER_PHONE).status, 'VERIFIED')

    def test_register_code_is_scoped_to_register_scene(self):
        self.send('login')
        rejected = self.client.post(
            '/api/auth/register',
            json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'new', 'password': 'password1', 'phone': PHONE, 'sms_code': CODE},
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(self.provider.check_calls, [])
        self.assertEqual(self.sms_record().status, 'SENT')

    def test_sms_login_rejects_register_scene_code(self):
        self.send('register')
        rejected = self.client.post(
            '/api/auth/login/sms', json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'phone': PHONE, 'sms_code': CODE}
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(self.provider.check_calls, [])
        self.assertEqual(self.sms_record().status, 'SENT')

    def test_register_code_is_consumed_on_success(self):
        self.send('register')
        response = self.client.post(
            '/api/auth/register',
            json={'accepted_terms_version': CURRENT_TERMS_VERSION, 'username': 'new', 'password': 'password1', 'phone': PHONE, 'sms_code': CODE},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.sms_record().status, 'CONSUMED')
        self.assertEqual(len(self.provider.check_calls), 1)

    def test_password_reset_consumes_code_and_rejects_reuse(self):
        self.add_user()
        self.send('reset_password')
        first = self.client.post(
            '/api/auth/forgot-password',
            json={'phone': PHONE, 'sms_code': CODE, 'new_password': 'new-password'},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.sms_record().status, 'CONSUMED')

        second = self.client.post(
            '/api/auth/forgot-password',
            json={'phone': PHONE, 'sms_code': CODE, 'new_password': 'reused-password'},
        )
        self.assertEqual(second.status_code, 400, second.text)
        with self.session_factory() as db:
            user = db.scalar(select(User).where(User.phone == PHONE))
            self.assertTrue(verify_password('new-password', user.password_hash))
            self.assertFalse(verify_password('reused-password', user.password_hash))
        self.assertEqual(len(self.provider.check_calls), 1)

    def test_password_reset_rejects_code_from_other_scene(self):
        self.add_user()
        self.send('register')
        response = self.client.post(
            '/api/auth/forgot-password',
            json={'phone': PHONE, 'sms_code': CODE, 'new_password': 'new-password'},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.provider.check_calls, [])
        self.assertEqual(self.sms_record().status, 'SENT')

    def test_bind_phone_requires_its_scene_and_consumes_code(self):
        user_id = self.add_user(phone=None)
        token = create_access_token(user_id, 'member')
        with self.session_factory() as db:
            db.add(UserSession(user_id=user_id, token_hash=token_fingerprint(token),
                               expires_at=datetime.utcfromtimestamp(decode_access_token(token)['exp'])))
            db.commit()
        headers = {'Authorization': f'Bearer {token}'}
        missing_phone = self.client.post('/api/auth/bind-phone', headers=headers, json={'sms_code': CODE})
        self.assertEqual(missing_phone.status_code, 422, missing_phone.text)
        missing_code = self.client.post('/api/auth/bind-phone', headers=headers, json={'phone': PHONE})
        self.assertEqual(missing_code.status_code, 422, missing_code.text)

        self.send('reset_password')
        rejected = self.client.post(
            '/api/auth/bind-phone', headers=headers, json={'phone': PHONE, 'sms_code': CODE}
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertEqual(self.provider.check_calls, [])
        self.assertEqual(self.sms_record().status, 'SENT')

        # An independent bind_phone proof permits binding exactly once.
        with self.session_factory() as db:
            prior = db.scalar(select(SmsVerificationRecord).where(SmsVerificationRecord.phone == PHONE))
            db.delete(prior)
            db.commit()
        self.send('bind_phone')
        bound = self.client.post(
            '/api/auth/bind-phone', headers=headers, json={'phone': PHONE, 'sms_code': CODE}
        )
        self.assertEqual(bound.status_code, 200, bound.text)
        self.assertEqual(bound.json()['phone'], PHONE)
        self.assertEqual(self.sms_record().status, 'CONSUMED')
        replay = self.client.post(
            '/api/auth/bind-phone', headers=headers, json={'phone': PHONE, 'sms_code': CODE}
        )
        self.assertEqual(replay.status_code, 400, replay.text)
        self.assertEqual(len(self.provider.check_calls), 1)


if __name__ == '__main__':
    unittest.main()
