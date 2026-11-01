"""邀请码真实落库回归：内存/临时 SQLite，无真实账号、短信或外部服务。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.routes.family import router as family_router
from app.api.routes.invite_codes import router as invite_router
from app.db.session import Base, get_db
from app.models import (AuditLog, Family, FamilyInviteCode, FamilyMember, FamilyMembership,
                        InviteCodeRateLimit, User)
from app.services.accounts import delete_user_data
from app.services.invite_codes import (RATE_WINDOW, join_by_code, refund_join_attempt,
                                      reserve_join_attempt, revoke_code)


class InviteCodesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:',
                                   connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.factory() as db:
            db.add_all([User(id=1, username='owner', password_hash='hash'),
                        User(id=2, username='joiner', password_hash='hash'),
                        User(id=3, username='viewer', password_hash='hash'),
                        User(id=4, username='unrelated', password_hash='hash')])
            db.flush()
            family = Family(owner_id=1, name='共享家谱')
            db.add(family)
            db.flush()
            self.family_id = family.id
            db.add(FamilyMembership(family_id=family.id, user_id=1, role='OWNER'))
            db.get(User, 1).active_family_id = family.id
            db.commit()
        self.user_id = 1
        api = FastAPI()
        api.include_router(family_router, prefix='/api')
        api.include_router(invite_router, prefix='/api')

        def isolated_db():
            with self.factory() as db:
                yield db

        def current_user(db=Depends(get_db)):
            if self.user_id is None:
                raise HTTPException(status_code=401, detail='请先登录')
            return db.get(User, self.user_id)

        api.dependency_overrides[get_db] = isolated_db
        api.dependency_overrides[get_current_user] = current_user
        self.client = TestClient(api)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def code(self, role='VIEWER'):
        response = self.client.post('/api/family/invite-codes', params={'family_id': self.family_id}, json={'role': role})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def join(self, code):
        return self.client.post('/api/family/join-by-code', json={'code': code})

    def test_code_creation_persists_seven_days_and_preserves_leading_zero(self):
        before = datetime.utcnow()
        with patch('app.services.invite_codes.secrets.randbelow', return_value=1):
            result = self.code('EDITOR')
        self.assertEqual(result['code'], '000001')
        self.assertEqual(result['role'], 'EDITOR')
        self.assertEqual(result['status'], 'PENDING')
        with self.factory() as db:
            row = db.get(FamilyInviteCode, result['id'])
            self.assertGreaterEqual(row.expires_at, before + timedelta(days=7))
            self.assertLess(row.expires_at, datetime.utcnow() + timedelta(days=7, seconds=1))
            self.assertIsNotNone(db.scalar(select(AuditLog).where(AuditLog.action == 'invite_code.create')))

    def test_unique_code_collision_retries_without_losing_other_records(self):
        with patch('app.services.invite_codes.secrets.randbelow', return_value=1):
            first = self.code()
        with patch('app.services.invite_codes.secrets.randbelow', side_effect=[1, 2]):
            second = self.code()
        self.assertEqual(first['code'], '000001')
        self.assertEqual(second['code'], '000002')
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(FamilyInviteCode)), 2)

    def test_owner_only_code_management_and_no_owner_role_assignment(self):
        code = self.code()
        with self.factory() as db:
            db.add_all([FamilyMembership(family_id=self.family_id, user_id=2, role='EDITOR'),
                        FamilyMembership(family_id=self.family_id, user_id=3, role='VIEWER')])
            db.commit()
        for user_id in (2, 3, 4):
            self.user_id = user_id
            self.assertEqual(self.client.get('/api/family/invite-codes', params={'family_id': self.family_id}).status_code, 403)
            self.assertEqual(self.client.post('/api/family/invite-codes', params={'family_id': self.family_id}, json={'role':'VIEWER'}).status_code, 403)
            self.assertEqual(self.client.delete(f'/api/family/invite-codes/{code["id"]}').status_code, 403)
        self.user_id = 1
        for role in ('OWNER', 'ADMIN', 'MEMBER', ''):
            self.assertEqual(self.client.post('/api/family/invite-codes', params={'family_id': self.family_id}, json={'role':role}).status_code, 422)
        memberships = self.client.get('/api/family/memberships', params={'family_id':self.family_id}).json()
        owner = next(row for row in memberships if row['user_id'] == 1)
        self.assertEqual(self.client.patch(f'/api/family/memberships/{owner["id"]}', params={'family_id':self.family_id}, json={'role':'VIEWER'}).status_code, 422)
        self.assertEqual(self.client.delete(f'/api/family/memberships/{owner["id"]}', params={'family_id':self.family_id}).status_code, 422)

    def test_join_is_authenticated_and_code_is_strict_ascii_string(self):
        for value in ('12345', '1234567', '１２３４５６', '١٢٣٤٥٦', '12345a', ' 12345', 123456, None):
            with self.subTest(value=value):
                self.assertEqual(self.join(value).status_code, 422)
        self.user_id = None
        self.assertEqual(self.join('123456').status_code, 401)
        self.assertEqual(self.client.post('/api/family/personal').status_code, 401)

    def test_join_keeps_personal_family_and_members_unchanged_then_switches(self):
        code = self.code('EDITOR')
        with self.factory() as db:
            personal = Family(owner_id=2, name='自己的谱', revision=3)
            db.add(personal)
            db.flush()
            db.add(FamilyMember(family_id=personal.id, client_id='self', name='个人成员'))
            db.add(FamilyMembership(family_id=personal.id, user_id=2, role='OWNER'))
            db.get(User, 2).active_family_id = personal.id
            personal_id = personal.id
            db.commit()
        self.user_id = 2
        result = self.join(code['code'])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['family_id'], self.family_id)
        self.assertEqual(result.json()['role'], 'EDITOR')
        self.assertEqual(result.json()['members'], [])
        with self.factory() as db:
            personal = db.get(Family, personal_id)
            self.assertEqual((personal.name, personal.revision), ('自己的谱', 3))
            self.assertEqual(db.scalar(select(FamilyMember.name).where(FamilyMember.family_id == personal_id)), '个人成员')
            self.assertEqual(db.get(User, 2).active_family_id, self.family_id)
            used = db.get(FamilyInviteCode, code['id'])
            self.assertEqual((used.status, used.used_by_user_id), ('USED', 2))
            self.assertIsNotNone(used.used_at)
        returned = self.client.post('/api/family/personal')
        self.assertEqual(returned.status_code, 200, returned.text)
        self.assertEqual(returned.json()['family_id'], personal_id)
        self.assertEqual(returned.json()['members'][0]['name'], '个人成员')
        self.assertEqual(returned.json()['role'], 'OWNER')

    def test_join_and_personal_interface_create_missing_personal_once(self):
        code = self.code()
        self.user_id = 2
        response = self.join(code['code'])
        self.assertEqual(response.status_code, 200, response.text)
        first = self.client.post('/api/family/personal').json()
        second = self.client.post('/api/family/personal').json()
        self.assertEqual(first['family_id'], second['family_id'])
        self.assertNotEqual(first['family_id'], self.family_id)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Family).where(Family.owner_id == 2)), 1)
            self.assertEqual(db.scalar(select(FamilyMembership.role).where(FamilyMembership.family_id == first['family_id'], FamilyMembership.user_id == 2)), 'OWNER')

    def test_existing_viewer_consuming_editor_code_keeps_viewer(self):
        code = self.code('EDITOR')
        with self.factory() as db:
            db.add(FamilyMembership(family_id=self.family_id, user_id=2, role='VIEWER'))
            db.commit()
        self.user_id = 2
        response = self.join(code['code'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['role'], 'VIEWER')
        with self.factory() as db:
            roles = db.scalars(select(FamilyMembership.role).where(FamilyMembership.family_id == self.family_id, FamilyMembership.user_id == 2)).all()
            self.assertEqual(roles, ['VIEWER'])
            self.assertEqual(db.get(FamilyInviteCode, code['id']).status, 'USED')

    def test_single_use_expiry_revoke_and_invalid_errors_are_uniform(self):
        used, expired, cancelled = self.code(), self.code(), self.code()
        revoke = self.client.delete(f'/api/family/invite-codes/{cancelled["id"]}')
        self.assertEqual(revoke.status_code, 200, revoke.text)
        self.assertEqual(revoke.json()['status'], 'CANCELLED')
        with self.factory() as db:
            db.get(FamilyInviteCode, expired['id']).expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.user_id = 2
        self.assertEqual(self.join(used['code']).status_code, 200)
        errors = [self.join(value) for value in (used['code'], expired['code'], cancelled['code'], '999999')]
        self.assertEqual([response.status_code for response in errors], [400]*4)
        self.assertEqual(len({response.json()['detail'] for response in errors}), 1)
        self.user_id = 1
        listed = self.client.get('/api/family/invite-codes', params={'family_id': self.family_id}).json()
        statuses = {row['id']:row['status'] for row in listed}
        self.assertEqual(statuses[expired['id']], 'EXPIRED')
        self.assertEqual(self.client.delete(f'/api/family/invite-codes/{used["id"]}').status_code, 409)

    def test_guess_rate_persists_and_resets_after_window(self):
        self.user_id = 2
        for _ in range(5):
            self.assertEqual(self.join('999999').status_code, 400)
        self.assertEqual(self.join('999999').status_code, 429)
        with self.factory() as db:
            bucket = db.get(InviteCodeRateLimit, 'user:2')
            self.assertEqual(bucket.attempts, 5)
            bucket.window_started_at = datetime.utcnow() - RATE_WINDOW - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.join('999999').status_code, 400)
        with self.factory() as db:
            self.assertEqual(db.get(InviteCodeRateLimit, 'user:2').attempts, 1)

    def test_user_and_network_rate_buckets_are_independent(self):
        with self.factory() as db:
            for i in range(5):
                reserve_join_attempt(db, 2, f'network-{i}')
            with self.assertRaises(HTTPException) as user_limit:
                reserve_join_attempt(db, 2, 'another-network')
            self.assertEqual(user_limit.exception.status_code, 429)
            for i in range(30):
                reserve_join_attempt(db, 100+i, 'same-network')
            with self.assertRaises(HTTPException) as network_limit:
                reserve_join_attempt(db, 1000, 'same-network')
            self.assertEqual(network_limit.exception.status_code, 429)
            self.assertEqual(db.get(InviteCodeRateLimit, 'user:2').attempts, 5)

    def test_success_refund_cannot_reduce_new_window_failures(self):
        with self.factory() as db:
            reserved = reserve_join_attempt(db, 2, 'network')
            next_window = datetime.utcnow() + RATE_WINDOW
            for key, _ in reserved:
                db.execute(update(InviteCodeRateLimit).where(InviteCodeRateLimit.key == key)
                           .values(window_started_at=next_window, attempts=4))
            db.commit()
            refund_join_attempt(db, reserved)
            db.commit()
            self.assertEqual(db.get(InviteCodeRateLimit, 'user:2').attempts, 4)

    def test_join_failure_rolls_back_used_status_personal_and_membership(self):
        code = self.code()
        self.user_id = 2
        with self.factory() as db:
            with patch('app.services.invite_codes.snapshot', side_effect=RuntimeError('模拟快照失败')):
                with self.assertRaises(RuntimeError):
                    join_by_code(db, db.get(User, 2), code['code'], 'network')
            self.assertEqual(db.get(FamilyInviteCode, code['id']).status, 'PENDING')
            self.assertIsNone(db.scalar(select(Family).where(Family.owner_id == 2)))
            self.assertIsNone(db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == self.family_id, FamilyMembership.user_id == 2)))
            self.assertEqual(db.get(InviteCodeRateLimit, 'user:2').attempts, 1)

    def test_pending_limit_and_collision_exhaustion_are_bounded(self):
        for _ in range(10):
            self.code()
        self.assertEqual(self.client.post('/api/family/invite-codes', params={'family_id':self.family_id}, json={'role':'VIEWER'}).status_code, 429)
        with self.factory() as db:
            rows = db.scalars(select(FamilyInviteCode)).all()
            for row in rows:
                row.status = 'CANCELLED'
            collision = int(rows[0].code)
            db.commit()
        with patch('app.services.invite_codes.secrets.randbelow', return_value=collision) as random:
            response = self.client.post('/api/family/invite-codes', params={'family_id':self.family_id}, json={'role':'VIEWER'})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(random.call_count, 40)

    def test_account_cleanup_removes_owned_created_used_codes_and_user_bucket(self):
        owner_code = self.code()
        shared_code = self.code()
        self.user_id = 2
        self.assertEqual(self.join(shared_code['code']).status_code, 200)
        personal = self.client.post('/api/family/personal').json()['family_id']
        self.user_id = 2
        created = self.client.post('/api/family/invite-codes', params={'family_id':personal}, json={'role':'VIEWER'})
        self.assertEqual(created.status_code, 201)
        self.user_id = 4
        self.client.post('/api/family/personal')
        with self.factory() as db:
            unrelated_family = db.scalar(select(Family).where(Family.owner_id == 4))
            unrelated_code = FamilyInviteCode(code='876543', family_id=unrelated_family.id, inviter_id=4,
                                              role='VIEWER', expires_at=datetime.utcnow()+timedelta(days=7))
            db.add(unrelated_code)
            db.commit()
            delete_user_data(db, db.get(User, 2))
            self.assertIsNone(db.get(User, 2))
            self.assertIsNone(db.get(InviteCodeRateLimit, 'user:2'))
            remaining = set(db.scalars(select(FamilyInviteCode.id)).all())
            self.assertIn(owner_code['id'], remaining)
            self.assertIn(unrelated_code.id, remaining)
            self.assertNotIn(shared_code['id'], remaining)
            self.assertNotIn(created.json()['id'], remaining)
            delete_user_data(db, db.get(User, 1))
            self.assertEqual(set(db.scalars(select(FamilyInviteCode.id)).all()), {unrelated_code.id})


class InviteCodeConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        database = Path(self.directory.name) / 'concurrency.sqlite'
        self.engine = create_engine(f'sqlite+pysqlite:///{database}', connect_args={'check_same_thread':False, 'timeout':20})
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        with self.factory() as db:
            db.add_all([User(id=i, username=f'user{i}', password_hash='hash') for i in range(1, 9)])
            db.flush()
            db.add(Family(id=1, owner_id=1, name='并发家族'))
            db.add(FamilyMembership(family_id=1, user_id=1, role='OWNER'))
            db.add_all([FamilyInviteCode(id=i, code=f'{i:06d}', family_id=1, inviter_id=1, role='VIEWER',
                                         expires_at=datetime.utcnow()+timedelta(days=7)) for i in (1, 2)])
            db.commit()

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def race(self, functions):
        barrier = threading.Barrier(len(functions))
        def run(function):
            barrier.wait(timeout=10)
            with self.factory() as db:
                try:
                    result = function(db)
                    return ('ok', result)
                except HTTPException as error:
                    db.rollback()
                    return ('http', error.status_code)
        with ThreadPoolExecutor(max_workers=len(functions)) as executor:
            return list(executor.map(run, functions))

    def test_two_users_can_consume_same_code_only_once(self):
        results = self.race([lambda db:join_by_code(db, db.get(User, 2), '000001', 'a'),
                             lambda db:join_by_code(db, db.get(User, 3), '000001', 'b')])
        self.assertEqual([kind for kind, _ in results].count('ok'), 1)
        self.assertEqual([kind for kind, _ in results].count('http'), 1)
        with self.factory() as db:
            code = db.get(FamilyInviteCode, 1)
            self.assertEqual(code.status, 'USED')
            members = db.scalars(select(FamilyMembership).where(FamilyMembership.family_id == 1, FamilyMembership.user_id != 1)).all()
            self.assertEqual([row.user_id for row in members], [code.used_by_user_id])

    def test_consume_and_revoke_have_one_terminal_winner(self):
        results = self.race([lambda db:join_by_code(db, db.get(User, 2), '000001', 'a'),
                             lambda db:revoke_code(db, db.get(User, 1), 1)])
        self.assertEqual([kind for kind, _ in results].count('ok'), 1)
        with self.factory() as db:
            code = db.get(FamilyInviteCode, 1)
            self.assertIn(code.status, {'USED','CANCELLED'})
            member = db.scalar(select(FamilyMembership).where(FamilyMembership.family_id == 1, FamilyMembership.user_id == 2))
            self.assertEqual(member is not None, code.status == 'USED')

    def test_concurrent_first_rate_bucket_creation_respects_user_limit(self):
        def reserve(db):
            return reserve_join_attempt(db, 2, 'shared-network')
        results = self.race([reserve for _ in range(8)])
        self.assertEqual([kind for kind, _ in results].count('ok'), 5)
        self.assertEqual([status for kind, status in results if kind == 'http'], [429]*3)
        with self.factory() as db:
            self.assertEqual(db.get(InviteCodeRateLimit, 'user:2').attempts, 5)
            self.assertEqual(db.scalar(select(func.count()).select_from(InviteCodeRateLimit)), 2)

    def test_two_codes_same_user_family_keep_one_membership_and_personal(self):
        results = self.race([lambda db:join_by_code(db, db.get(User, 2), '000001', 'a'),
                             lambda db:join_by_code(db, db.get(User, 2), '000002', 'b')])
        self.assertEqual([kind for kind, _ in results].count('ok'), 2)
        with self.factory() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(FamilyMembership).where(FamilyMembership.family_id == 1, FamilyMembership.user_id == 2)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(Family).where(Family.owner_id == 2)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(FamilyInviteCode).where(FamilyInviteCode.status == 'USED')), 2)


if __name__ == '__main__':
    unittest.main()
