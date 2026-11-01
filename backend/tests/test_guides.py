"""账号导览真实持久化、上海日期及注销清理，使用隔离 SQLite。"""
from datetime import date, datetime, timezone
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import router as auth_router
from app.api.routes.guides import guide_today, router as guides_router
from app.core.security import hash_password
from app.core.legal import CURRENT_TERMS_VERSION
from app.db.session import Base, get_db
from app.models import User
from app.models.guides import UserGuideSetting


class GuideSettingsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:',
            connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.factory() as db:
            first = User(username='guide-first', password_hash=hash_password('password1'))
            second = User(username='guide-second', password_hash=hash_password('password1'))
            db.add_all([first, second]); db.commit()
            self.first_id, self.second_id = first.id, second.id
        api = FastAPI()
        api.include_router(auth_router, prefix='/api')
        api.include_router(guides_router, prefix='/api')
        def isolated_db():
            with self.factory() as db:
                yield db
        api.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(api)
        self.headers = self.login('guide-first')
        self.other_headers = self.login('guide-second')

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def login(self, username):
        result = self.client.post('/api/auth/login', json={'username': username, 'password': 'password1', 'accepted_terms_version': CURRENT_TERMS_VERSION})
        self.assertEqual(result.status_code, 200, result.text)
        return {'Authorization': 'Bearer ' + result.json()['access_token']}

    def change(self, dismissal, headers=None):
        result = self.client.put('/api/auth/guides', json={'dismissal': dismissal}, headers=headers or self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def read(self, headers=None):
        result = self.client.get('/api/auth/guides', headers=headers or self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_default_is_visible_and_does_not_create_unnecessary_row(self):
        self.assertEqual(self.read(), {'permanently_hidden': False, 'dismissed_on': None, 'show_on_login': True})
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UserGuideSetting)), 0)

    def test_today_persists_across_sessions_and_expires_next_shanghai_date(self):
        with patch('app.api.routes.guides.guide_today', return_value=date(2026, 10, 13)):
            self.assertEqual(self.change('today'), {
                'permanently_hidden': False, 'dismissed_on': '2026-10-13', 'show_on_login': False})
            fresh_session = self.login('guide-first')
            self.assertFalse(self.read(fresh_session)['show_on_login'])
            self.assertTrue(self.read(self.other_headers)['show_on_login'])
            with self.factory() as db:
                row = db.get(UserGuideSetting, self.first_id)
                self.assertEqual(row.dismissed_on, date(2026, 10, 13))
        with patch('app.api.routes.guides.guide_today', return_value=date(2026, 10, 14)):
            self.assertTrue(self.read()['show_on_login'])
            self.assertEqual(self.read()['dismissed_on'], '2026-10-13')

    def test_permanent_persists_and_reset_restores_future_logins(self):
        with patch('app.api.routes.guides.guide_today', return_value=date(2026, 10, 13)):
            self.change('today')
            self.assertEqual(self.change('permanent'), {
                'permanently_hidden': True, 'dismissed_on': None, 'show_on_login': False})
        with patch('app.api.routes.guides.guide_today', return_value=date(2027, 1, 1)):
            self.assertFalse(self.read(self.login('guide-first'))['show_on_login'])
            self.assertEqual(self.change('reset'), {
                'permanently_hidden': False, 'dismissed_on': None, 'show_on_login': True})
            self.assertTrue(self.read()['show_on_login'])
            with self.factory() as db:
                self.assertEqual(db.scalar(select(func.count()).select_from(UserGuideSetting)), 1)

    def test_complete_modes_replace_previous_choice_and_one_row_per_account(self):
        with patch('app.api.routes.guides.guide_today', return_value=date(2026, 10, 13)):
            self.change('permanent')
            self.assertFalse(self.change('today')['permanently_hidden'])
            self.change('today')
            self.change('permanent')
            self.change('permanent', self.other_headers)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(UserGuideSetting)), 2)
            self.assertTrue(db.get(UserGuideSetting, self.first_id).permanently_hidden)
            self.assertTrue(db.get(UserGuideSetting, self.second_id).permanently_hidden)

    def test_authentication_and_request_validation(self):
        self.assertEqual(self.client.get('/api/auth/guides').status_code, 401)
        self.assertEqual(self.client.put('/api/auth/guides', json={'dismissal': 'today'}).status_code, 401)
        for payload in ({}, {'dismissal': 'week'}, {'dismissal': None},
                        {'dismissal': 'today', 'user_id': self.second_id}):
            result = self.client.put('/api/auth/guides', json=payload, headers=self.headers)
            self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(self.client.post('/api/auth/logout', headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/guides', headers=self.headers).status_code, 401)

    def test_deleted_account_removes_only_its_guide_setting(self):
        self.change('permanent')
        self.change('today', self.other_headers)
        deleted = self.client.delete('/api/auth/me', headers=self.headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        with self.factory() as db:
            self.assertIsNone(db.get(UserGuideSetting, self.first_id))
            self.assertIsNotNone(db.get(UserGuideSetting, self.second_id))
        self.assertEqual(self.client.get('/api/auth/guides', headers=self.headers).status_code, 401)
        self.assertFalse(self.read(self.other_headers)['show_on_login'])

    def test_shanghai_date_rolls_at_utc_1600_even_if_host_timezone_differs(self):
        self.assertEqual(guide_today(datetime(2026, 10, 12, 15, 59, 59, tzinfo=timezone.utc)), date(2026, 10, 12))
        self.assertEqual(guide_today(datetime(2026, 10, 12, 16, 0, 0, tzinfo=timezone.utc)), date(2026, 10, 13))
        self.assertEqual(guide_today(datetime(2026, 10, 12, 16, 0, 0)), date(2026, 10, 13))

    def test_guides_route_is_exposed_by_actual_application(self):
        from app.main import app
        api = app.app
        prior = api.dependency_overrides.copy()
        def isolated_db():
            with self.factory() as db:
                yield db
        api.dependency_overrides[get_db] = isolated_db
        try:
            # 不启动真实应用 lifespan，仅验证实际注册的路由及独立数据库读取。
            actual_client = TestClient(app)
            try:
                response = actual_client.put('/api/auth/guides', headers=self.headers, json={'dismissal': 'permanent'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertFalse(actual_client.get('/api/auth/guides', headers=self.headers).json()['show_on_login'])
            finally:
                actual_client.close()
        finally:
            api.dependency_overrides = prior

    def test_new_table_is_registered_and_compatible_with_both_supported_databases(self):
        from sqlalchemy.schema import CreateTable
        self.assertIn('user_guide_settings', Base.metadata.tables)
        import app.models as registered_models
        self.assertIs(registered_models.UserGuideSetting, UserGuideSetting)
        for dialect in (sqlite.dialect(), mysql.dialect()):
            ddl = str(CreateTable(UserGuideSetting.__table__).compile(dialect=dialect))
            self.assertIn('PRIMARY KEY (user_id)', ddl)
            self.assertIn('ON DELETE CASCADE', ddl)


if __name__ == '__main__':
    unittest.main()
