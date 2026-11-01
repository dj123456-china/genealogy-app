"""条款确认在认证前校验，并仅为用户本次明确同意留下证据。"""

import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import auth
from app.core.legal import CURRENT_TERMS_VERSION
from app.core.security import hash_password, token_fingerprint
from app.db import session as db_session
from app.db.session import Base, get_db
from app.models import LoginLog, SmsVerificationRecord, User, UserSession
from app.services import sms
from test_auth_sms import CODE, PHONE, FakeSmsClient


class TermsAuthenticationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:',
                                    connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.provider = FakeSmsClient()
        self.provider_patch = patch.object(sms, '_client', return_value=self.provider)
        self.provider_patch.start()
        app = FastAPI()
        app.include_router(auth.router, prefix='/api')

        def database():
            with self.factory() as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.provider_patch.stop()
        self.engine.dispose()

    def add_user(self):
        with self.factory() as db:
            user = User(username='member', phone=PHONE, password_hash=hash_password('password1'))
            db.add(user)
            db.commit()
            return user.id

    def send_code(self, scene):
        result = self.client.post('/api/auth/send-sms', json={'phone': PHONE, 'scene': scene})
        self.assertEqual(result.status_code, 200, result.text)

    def assert_acceptance(self, response, before, expected_status=200):
        self.assertEqual(response.status_code, expected_status, response.text)
        with self.factory() as db:
            record = db.scalar(select(UserSession).where(
                UserSession.token_hash == token_fingerprint(response.json()['access_token'])))
            self.assertIsNotNone(record)
            self.assertEqual(record.accepted_terms_version, CURRENT_TERMS_VERSION)
            self.assertGreaterEqual(record.terms_accepted_at, before)
            self.assertLessEqual(record.terms_accepted_at, datetime.utcnow())

    def test_missing_or_noncurrent_terms_reject_before_password_sms_or_account_creation(self):
        self.add_user()
        cases = (
            ('/api/auth/login', {'username': 'member', 'password': 'password1'}),
            ('/api/auth/login', {'phone': PHONE, 'password': 'password1'}),
            ('/api/auth/login/sms', {'phone': PHONE, 'sms_code': CODE}),
            ('/api/auth/sms-login', {'phone': PHONE, 'sms_code': CODE}),
            ('/api/auth/register', {'username': 'new', 'password': 'password1',
                                    'phone': '13900139000', 'sms_code': CODE}),
        )
        with patch.object(auth, 'check_sms_code') as sms_check, \
             patch.object(auth, 'verify_password') as password_check:
            for path, payload in cases:
                for version in (None, '', '2026-10-01-v1', False):
                    with self.subTest(path=path, version=version):
                        submitted = dict(payload)
                        if version is not None:
                            submitted['accepted_terms_version'] = version
                        response = self.client.post(path, json=submitted)
                        self.assertEqual(response.status_code, 422, response.text)
                        self.assertTrue(any(error['loc'][-1] == 'accepted_terms_version'
                                            for error in response.json()['detail']))
            sms_check.assert_not_called()
            password_check.assert_not_called()
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(UserSession)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(LoginLog)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(SmsVerificationRecord)), 0)
        self.assertEqual(self.provider.check_calls, [])

    def test_password_logins_record_current_version_and_server_utc_time(self):
        self.add_user()
        for identifier in ({'username': 'member'}, {'phone': PHONE}):
            before = datetime.utcnow()
            response = self.client.post('/api/auth/login', json={
                **identifier, 'password': 'password1',
                'accepted_terms_version': CURRENT_TERMS_VERSION,
                'terms_accepted_at': '2000-01-01T00:00:00Z',
            })
            self.assert_acceptance(response, before)

    def test_sms_login_and_alias_record_current_terms(self):
        self.add_user()
        for path in ('/api/auth/login/sms', '/api/auth/sms-login'):
            # Each scene proof is consumable once; clear the prior proof to
            # request another SMS without waiting for the rate-limit window.
            with self.factory() as db:
                for proof in db.scalars(select(SmsVerificationRecord)):
                    db.delete(proof)
                db.commit()
            self.send_code('login')
            before = datetime.utcnow()
            response = self.client.post(path, json={
                'phone': PHONE, 'sms_code': CODE,
                'accepted_terms_version': CURRENT_TERMS_VERSION,
            })
            self.assert_acceptance(response, before)

    def test_direct_registration_records_terms(self):
        self.send_code('register')
        before = datetime.utcnow()
        response = self.client.post('/api/auth/register', json={
            'username': 'new', 'password': 'password1', 'phone': PHONE, 'sms_code': CODE,
            'accepted_terms_version': CURRENT_TERMS_VERSION,
        })
        self.assert_acceptance(response, before, 201)

    def test_new_phone_handoff_requires_confirmation_again_at_registration(self):
        self.send_code('login')
        handoff = self.client.post('/api/auth/login/sms', json={
            'phone': PHONE, 'sms_code': CODE, 'accepted_terms_version': CURRENT_TERMS_VERSION,
        })
        self.assertEqual(handoff.status_code, 200, handoff.text)
        token = handoff.json()['registration_token']
        payload = {'username': 'new', 'password': 'password1', 'phone': PHONE,
                   'registration_token': token}
        rejected = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(rejected.status_code, 422, rejected.text)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(User)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(UserSession)), 0)
            self.assertEqual(db.scalar(select(SmsVerificationRecord)).status, 'VERIFIED')
        before = datetime.utcnow()
        response = self.client.post('/api/auth/register', json={
            **payload, 'accepted_terms_version': CURRENT_TERMS_VERSION,
        })
        self.assert_acceptance(response, before, 201)

    def test_token_issuance_without_confirmation_does_not_fabricate_acceptance(self):
        user_id = self.add_user()
        with self.factory() as db:
            auth.token_response(db.get(User, user_id), db)
            record = db.scalar(select(UserSession))
            self.assertIsNone(record.accepted_terms_version)
            self.assertIsNone(record.terms_accepted_at)


class TermsMigrationTest(unittest.TestCase):
    def test_additive_migration_keeps_legacy_acceptance_unknown_and_preserves_new_records(self):
        engine = create_engine('sqlite+pysqlite:///:memory:')
        self.addCleanup(engine.dispose)
        with engine.begin() as db:
            db.execute(text('CREATE TABLE user_sessions (id INTEGER PRIMARY KEY, user_id INTEGER, '
                            'token_hash VARCHAR(128), expires_at DATETIME, revoked_at DATETIME, '
                            'created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'))
            db.execute(text("INSERT INTO user_sessions (id,user_id,token_hash,expires_at) "
                            "VALUES (1,10,'legacy','2030-01-01')"))
        with patch.object(db_session, 'engine', engine):
            db_session.ensure_schema()
            with engine.begin() as db:
                old = db.execute(text('SELECT user_id,token_hash,accepted_terms_version,terms_accepted_at '
                                      'FROM user_sessions WHERE id=1')).first()
                self.assertEqual(old, (10, 'legacy', None, None))
                db.execute(text('INSERT INTO user_sessions '
                                '(id,user_id,token_hash,expires_at,accepted_terms_version,terms_accepted_at) '
                                "VALUES (2,10,'current','2030-01-01',:version,'2026-10-13 01:02:03')"),
                           {'version': CURRENT_TERMS_VERSION})
            db_session.ensure_schema()
        columns = {column['name']: column for column in inspect(engine).get_columns('user_sessions')}
        self.assertEqual(columns['accepted_terms_version']['type'].length, 32)
        self.assertTrue(columns['accepted_terms_version']['nullable'])
        self.assertTrue(columns['terms_accepted_at']['nullable'])
        with engine.connect() as db:
            rows = db.execute(text('SELECT id,accepted_terms_version,terms_accepted_at '
                                   'FROM user_sessions ORDER BY id')).all()
            self.assertEqual(rows, [(1, None, None), (2, CURRENT_TERMS_VERSION, '2026-10-13 01:02:03')])


if __name__ == '__main__':
    unittest.main()
