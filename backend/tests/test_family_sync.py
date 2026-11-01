"""头像容量及同步接口错误响应回归测试，使用独立内存数据库。"""

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.db.session import Base, get_db
from app.db import session as db_session
from app.main import app
from app.models import Family
from app.schemas.family import FamilyProfile


class FamilySyncTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            'sqlite+pysqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        factory = sessionmaker(bind=self.engine, expire_on_commit=False)

        def isolated_db():
            with factory() as db:
                yield db

        self.api = app.app
        self.previous_overrides = self.api.dependency_overrides.copy()
        self.api.dependency_overrides[get_db] = isolated_db
        self.api.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
        self.client = TestClient(app, raise_server_exceptions=False)
        self.headers = {'Origin': 'http://localhost:5173'}

    def tearDown(self):
        self.client.close()
        self.api.dependency_overrides = self.previous_overrides
        self.engine.dispose()

    def test_two_mib_avatar_sync_round_trip(self):
        avatar = 'data:image/png;base64,' + base64.b64encode(b'x' * (2 * 1024 * 1024)).decode()
        current = self.client.get('/api/family/sync').json()
        payload = {'family_id': current['family_id'], 'revision': current['revision'], 'profile': {'name': '测试家族', 'avatar': avatar}, 'members': [], 'reminders': []}
        response = self.client.put('/api/family/sync', json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(response.json()['profile'], payload['profile'])
        self.assertEqual(response.headers['access-control-allow-origin'], self.headers['Origin'])
        saved = self.client.get('/api/family/sync')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['profile'], payload['profile'])

    def test_mysql_avatar_column_supports_base64_images(self):
        self.assertEqual(Family.__table__.c.avatar.type.compile(dialect=mysql.dialect()), 'MEDIUMTEXT')

    def test_existing_mysql_text_with_collation_is_migrated_once(self):
        engine = MagicMock()
        engine.dialect.name = 'mysql'
        inspector = MagicMock()
        inspector.get_table_names.return_value = ['families']
        inspector.get_columns.side_effect = [
            [{'name': 'avatar', 'type': mysql.TEXT(collation='utf8mb4_unicode_ci')}, {'name': 'revision'}],
            [{'name': 'avatar', 'type': mysql.MEDIUMTEXT(collation='utf8mb4_unicode_ci')}, {'name': 'revision'}],
        ]
        with patch.object(db_session, 'engine', engine), patch.object(db_session, 'inspect', return_value=inspector):
            db_session.ensure_schema()
            db_session.ensure_schema()
        execute = engine.begin.return_value.__enter__.return_value.execute
        execute.assert_called_once()
        self.assertEqual(str(execute.call_args.args[0]), 'ALTER TABLE families MODIFY COLUMN avatar MEDIUMTEXT NOT NULL')

    def test_unhandled_sync_failure_keeps_cors_headers(self):
        with patch('app.services.family.family_for', side_effect=RuntimeError('test failure')):
            response = self.client.put('/api/family/sync', json={'family_id': 1, 'revision': 0}, headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers['access-control-allow-origin'], self.headers['Origin'])

    def test_avatar_limit_is_still_enforced(self):
        with self.assertRaises(ValidationError):
            FamilyProfile(avatar='x' * 2_800_001)


if __name__ == '__main__':
    unittest.main()
