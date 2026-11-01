"""家族业务端到端回归，独立 SQLite，覆盖真实落库和权限边界。"""
import copy
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.routes.family import router
from app.db import session as db_session
from app.db.session import Base, get_db
from app.models import (AuditLog, Family, FamilyMember, FamilyMembership, FamilyRelationship,
                        Invitation, NotificationRecord, Reminder, User, WechatDelivery)
from app.services.notification_access import can_receive_family_notification


class FamilyBusinessTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        with self.factory() as db:
            db.add_all([User(id=1, username='owner', phone='13800000001', password_hash='hash'),
                        User(id=2, username='editor', phone='13800000002', password_hash='hash'),
                        User(id=3, username='viewer', phone='13800000003', password_hash='hash')])
            db.commit()
        self.user_id = 1
        app = FastAPI()
        app.include_router(router, prefix='/api')

        def database():
            with self.factory() as db:
                yield db

        def current(db=__import__('fastapi').Depends(get_db)):
            return db.get(User, self.user_id)

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_current_user] = current
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def get_snapshot(self):
        response = self.client.get('/api/family/sync')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_explicit_family_context_ignores_other_devices_active_selection(self):
        owned = self.get_snapshot()['family_id']
        with self.factory() as db:
            shared = Family(owner_id=2, name='另一设备当前家族', avatar='')
            db.add(shared); db.flush()
            db.add(FamilyMembership(family_id=shared.id, user_id=1, role='EDITOR'))
            db.get(User, 1).active_family_id = shared.id
            db.commit()
        response = self.client.post('/api/family/invitations', params={'family_id': owned}, json={'invitee':'viewer','role':'VIEWER'})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['family_id'], owned)
        invites = self.client.get('/api/family/invitations', params={'family_id':owned})
        self.assertEqual(invites.status_code, 200)
        self.assertEqual(len(invites.json()), 1)
        members = self.client.get('/api/family/memberships', params={'family_id':owned})
        self.assertEqual(members.status_code, 200)
        self.assertEqual([m['role'] for m in members.json()], ['OWNER'])
        profile = self.client.get('/api/family/profile', params={'family_id':owned})
        self.assertEqual(profile.status_code, 200)
        self.assertNotEqual(profile.json()['name'], '另一设备当前家族')

    def save(self, data, expected=200):
        response = self.client.put('/api/family/sync', json=data)
        self.assertEqual(response.status_code, expected, response.text[:500])
        return response

    def family_data(self):
        data = self.get_snapshot()
        data['members'] = [
            {'client_id': 'father', 'name': '同名', 'relation': '父亲', 'generation': 1, 'birthday': '1950-01-01', 'spouse_client_id': 'mother'},
            {'client_id': 'mother', 'name': '母亲', 'generation': 1},
            {'client_id': 'child', 'name': '同名', 'relation': '本人', 'generation': 2,
             'birthday': '1980-01-01', 'parent_client_ids': ['father', 'mother'], 'death_year': 2018},
        ]
        data['reminders'] = [{'client_id': 'birthday-child', 'title': '子女生辰', 'type': 'birthday',
                              'member_client_id': 'child', 'date': '1980-01-01', 'advance': '提前 7 天'}]
        return data

    def test_sync_preserves_database_ids_and_materializes_bidirectional_relationships(self):
        first = self.save(self.family_data()).json()
        first_ids = {m['client_id']: m['id'] for m in first['members']}
        reminder_id = first['reminders'][0]['id']
        self.assertEqual(first['revision'], 1)
        self.assertEqual(first['members'][1]['spouse_client_id'], 'father')
        self.assertEqual(first['members'][2]['death_year'], '2018')
        self.assertTrue(first['members'][2]['deceased'])
        self.assertEqual(first['reminders'][0]['advance'], '提前7天')
        second_data = copy.deepcopy(first)
        second_data['members'][2]['bio'] = '第二次编辑'
        second = self.save(second_data).json()
        self.assertEqual(first_ids, {m['client_id']: m['id'] for m in second['members']})
        self.assertEqual(reminder_id, second['reminders'][0]['id'])
        self.assertEqual(second['revision'], 2)
        with self.factory() as db:
            rows = db.scalars(select(FamilyRelationship)).all()
            self.assertEqual(len(rows), 3)
            self.assertEqual(sum(r.kind == 'spouse' for r in rows), 1)
            self.assertGreater(len(db.scalars(select(AuditLog)).all()), 2)

    def test_stale_snapshot_cannot_delete_other_devices_new_member(self):
        old = self.get_snapshot()
        new = copy.deepcopy(old)
        new['members'] = [{'client_id': 'new-person', 'name': '新成员'}]
        saved = self.save(new).json()
        response = self.save(old, expected=409)
        self.assertEqual(response.json()['detail']['remote']['revision'], saved['revision'])
        self.assertEqual(self.get_snapshot()['members'][0]['name'], '新成员')

    def test_mother_only_parent_role_survives_unknown_gender_sync_and_edit(self):
        data = self.get_snapshot()
        data['members'] = [
            {'client_id': 'mother', 'name': '母亲', 'gender': '未知'},
            {'client_id': 'child', 'name': '子女', 'parent_client_ids': ['mother'],
             'parent_roles': ['mother']},
        ]
        saved = self.save(data).json()
        mother = next(member for member in saved['members'] if member['client_id'] == 'mother')
        child = next(member for member in saved['members'] if member['client_id'] == 'child')
        self.assertEqual(mother['gender'], '未知')
        self.assertEqual(child['parent_ids'], [mother['id']])
        self.assertEqual(child['parent_client_ids'], ['mother'])
        self.assertEqual(child['parent_roles'], ['mother'])
        with self.factory() as db:
            stored = db.get(FamilyMember, child['id'])
            self.assertEqual(json.loads(stored.parent_roles), ['mother'])
            self.assertEqual(json.loads(stored.parent_ids), [mother['id']])
        fetched = self.get_snapshot()
        child = next(member for member in fetched['members'] if member['client_id'] == 'child')
        child['bio'] = '同步后再次编辑'
        edited = self.save(fetched).json()
        child = next(member for member in edited['members'] if member['client_id'] == 'child')
        self.assertEqual(child['bio'], '同步后再次编辑')
        self.assertEqual(child['parent_client_ids'], ['mother'])
        self.assertEqual(child['parent_roles'], ['mother'])

    def test_deleting_father_keeps_mother_role_at_remaining_parent_position(self):
        data = self.family_data()
        data['members'][2]['parent_roles'] = ['father', 'mother']
        saved = self.save(data).json()
        child = next(member for member in saved['members'] if member['client_id'] == 'child')
        self.assertEqual(child['parent_roles'], ['father', 'mother'])
        father = next(member for member in saved['members'] if member['client_id'] == 'father')
        response = self.client.delete(f'/api/family/members/{father["id"]}',
                                      params={'family_id': saved['family_id'], 'revision': saved['revision']})
        self.assertEqual(response.status_code, 200, response.text)
        fetched = self.get_snapshot()
        mother = next(member for member in fetched['members'] if member['client_id'] == 'mother')
        child = next(member for member in fetched['members'] if member['client_id'] == 'child')
        self.assertEqual(child['parent_ids'], [mother['id']])
        self.assertEqual(child['parent_client_ids'], ['mother'])
        self.assertEqual(child['parent_roles'], ['mother'])
        child['name'] = '删除父亲后编辑'
        edited = self.save(fetched).json()
        child = next(member for member in edited['members'] if member['client_id'] == 'child')
        self.assertEqual(child['parent_roles'], ['mother'])
        with self.factory() as db:
            self.assertEqual(json.loads(db.get(FamilyMember, child['id']).parent_roles), ['mother'])
            relationships = db.scalars(select(FamilyRelationship)).all()
            self.assertEqual([(row.from_member_id, row.to_member_id, row.kind) for row in relationships],
                             [(mother['id'], child['id'], 'parent')])

    def test_parent_roles_accept_database_parent_ids_in_direct_member_create(self):
        data = self.get_snapshot()
        data['members'] = [{'client_id': 'mother', 'name': '母亲', 'gender': '未知'}]
        saved = self.save(data).json()
        mother = saved['members'][0]
        response = self.client.post('/api/family/members',
                                    params={'family_id': saved['family_id'], 'revision': saved['revision']},
                                    json={'client_id': 'child', 'name': '子女',
                                          'parent_ids': [mother['id']], 'parent_roles': ['mother']})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['parent_ids'], [mother['id']])
        self.assertEqual(response.json()['parent_client_ids'], ['mother'])
        self.assertEqual(response.json()['parent_roles'], ['mother'])
        fetched = self.get_snapshot()
        child = next(member for member in fetched['members'] if member['client_id'] == 'child')
        self.assertEqual(child['parent_roles'], ['mother'])

    def test_parent_role_length_duplicates_and_unknown_roles_are_rejected(self):
        cases = [
            ([], ['mother']),
            (['father'], ['father', 'mother']),
            (['father', 'mother'], ['mother']),
            (['father', 'mother'], ['father', 'father']),
            (['father', 'mother'], ['mother', 'mother']),
            (['mother'], ['unknown']),
        ]
        for parents, roles in cases:
            with self.subTest(parents=parents, roles=roles):
                data = self.get_snapshot()
                data['members'] = [
                    {'client_id': 'father', 'name': '父亲'},
                    {'client_id': 'mother', 'name': '母亲'},
                    {'client_id': 'child', 'name': '子女',
                     'parent_client_ids': parents, 'parent_roles': roles},
                ]
                self.save(data, expected=422)
                self.assertEqual(self.get_snapshot()['revision'], 0)
                self.assertEqual(self.get_snapshot()['members'], [])

    def test_generic_parent_roles_and_legacy_empty_roles_remain_supported(self):
        data = self.family_data()
        legacy = self.save(data).json()
        child = next(member for member in legacy['members'] if member['client_id'] == 'child')
        self.assertEqual(child['parent_client_ids'], ['father', 'mother'])
        self.assertEqual(child['parent_roles'], [])
        child['parent_roles'] = ['parent', 'parent']
        saved = self.save(legacy).json()
        child = next(member for member in saved['members'] if member['client_id'] == 'child')
        self.assertEqual(child['parent_roles'], ['parent', 'parent'])
        with self.factory() as db:
            self.assertEqual(json.loads(db.get(FamilyMember, child['id']).parent_roles), ['parent', 'parent'])

    def test_sync_requires_family_identity_and_revision(self):
        self.save({'members': []}, expected=422)
        data = self.get_snapshot()
        self.user_id = 2
        self.save(data, expected=403)
        self.assertEqual(self.get_snapshot()['members'], [])

    def test_graph_rejects_cycles_missing_nodes_duplicate_ids_and_conflicting_spouses(self):
        cases = [
            [{'client_id': 'a', 'name': 'A', 'parent_client_ids': ['b']}, {'client_id': 'b', 'name': 'B', 'parent_client_ids': ['a']}],
            [{'client_id': 'a', 'name': 'A', 'parent_client_ids': ['absent']}],
            [{'client_id': 'a', 'name': 'A'}, {'client_id': 'a', 'name': 'B'}],
            [{'client_id': 'a', 'name': 'A', 'spouse_client_id': 'b'}, {'client_id': 'b', 'name': 'B', 'spouse_client_id': 'c'}, {'client_id': 'c', 'name': 'C'}],
            [{'client_id': 'a', 'name': 'A', 'parent_client_ids': ['a']}],
            [{'client_id': 'a', 'name': 'A', 'parent_client_ids': ['b'], 'spouse_client_id': 'b'}, {'client_id': 'b', 'name': 'B'}],
        ]
        for members in cases:
            with self.subTest(members=members):
                data = self.get_snapshot()
                data['members'] = members
                self.save(data, expected=422)
                self.assertEqual(self.get_snapshot()['revision'], 0)

    def test_invalid_dates_and_lunar_fields_are_rejected(self):
        data = self.get_snapshot()
        data['members'] = [{'client_id': 'a', 'name': 'A', 'birthday': '2000-02-31'}]
        self.save(data, expected=422)
        data['members'] = [{'client_id': 'a', 'name': 'A', 'birthday': '9999-01-01'}]
        self.save(data, expected=422)
        data['members'] = [{'client_id': 'a', 'name': 'A', 'death_year': '9999'}]
        self.save(data, expected=422)
        data['members'] = [{'client_id': 'a', 'name': 'A', 'birthday': '1990-01-01', 'death_date': '1980-01-01'}]
        self.save(data, expected=422)
        data['members'] = [{'client_id': 'a', 'name': 'A', 'death_year': '2000', 'death_date': '2001-01-01'}]
        self.save(data, expected=422)
        data['members'] = []
        data['reminders'] = [{'client_id': 'r', 'title': '祭日', 'date': '2026-01-01', 'calendar_type': 'lunar'}]
        self.save(data, expected=422)
        data['reminders'][0].update(lunar_month=1, lunar_day=15, is_leap=False)
        saved = self.save(data).json()
        self.assertEqual(saved['reminders'][0]['calendar_type'], 'lunar')
        self.assertEqual(saved['reminders'][0]['lunar_day'], 15)

    def test_direct_crud_uses_same_revision_graph_and_audit(self):
        saved = self.save(self.family_data()).json()
        family_id, revision = saved['family_id'], saved['revision']
        child = next(m for m in saved['members'] if m['client_id'] == 'child')
        query = f'?family_id={family_id}&revision={revision}'
        changed = {**child, 'name': '改名'}
        update_response = self.client.put(f'/api/family/members/{child["id"]}{query}', json=changed)
        self.assertEqual(update_response.status_code, 200, update_response.text)
        self.assertEqual(update_response.json()['name'], '改名')
        current = self.get_snapshot()
        self.assertEqual(current['revision'], revision + 1)
        father = next(m for m in current['members'] if m['client_id'] == 'father')
        response = self.client.delete(f'/api/family/members/{father["id"]}?family_id={family_id}&revision={current["revision"]}')
        self.assertEqual(response.status_code, 200, response.text)
        current = self.get_snapshot()
        mother = next(m for m in current['members'] if m['client_id'] == 'mother')
        child = next(m for m in current['members'] if m['client_id'] == 'child')
        self.assertIsNone(mother['spouse_id'])
        self.assertEqual(child['parent_client_ids'], ['mother'])
        self.assertEqual(len(self.client.get('/api/family/relationships').json()), 1)
        response = self.client.post(f'/api/family/reminders?family_id={family_id}&revision={current["revision"]}', json={'title': '新提醒', 'date': '2027-02-01', 'member_client_id': 'mother'})
        self.assertEqual(response.status_code, 201, response.text)
        reminder = response.json()
        current = self.get_snapshot()
        response = self.client.put(f'/api/family/reminders/{reminder["id"]}?family_id={family_id}&revision={current["revision"]}', json={**reminder, 'title': '更新提醒'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['id'], reminder['id'])
        current = self.get_snapshot()
        response = self.client.delete(f'/api/family/reminders/{reminder["id"]}?family_id={family_id}&revision={current["revision"]}')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreater(len(self.client.get('/api/family/audit').json()), 5)

    def test_invitation_accept_role_edit_revoke_and_family_switch(self):
        owner_data = self.save(self.family_data()).json()
        owner_family = owner_data['family_id']
        invitation = self.client.post('/api/family/invitations', json={'invitee': '13800000002', 'role': 'EDITOR'})
        self.assertEqual(invitation.status_code, 201, invitation.text)
        invitation_id = invitation.json()['id']
        self.user_id = 3
        self.assertEqual(self.client.post(f'/api/family/invitations/{invitation_id}/accept').status_code, 403)
        self.user_id = 2
        personal = self.get_snapshot()
        incoming = self.client.get('/api/family/invitations/incoming').json()
        self.assertEqual(incoming[0]['id'], invitation_id)
        accepted = self.client.post(f'/api/family/invitations/{invitation_id}/accept')
        self.assertEqual(accepted.status_code, 200, accepted.text)
        shared = accepted.json()
        self.assertEqual(shared['role'], 'EDITOR')
        self.assertEqual(shared['family_id'], owner_family)
        shared['profile']['name'] = '编辑者修改'
        saved = self.save(shared).json()
        self.assertEqual(self.client.post('/api/family/invitations', json={'invitee': 'viewer'}).status_code, 403)
        families = self.client.get('/api/family/list').json()
        self.assertEqual(len(families), 2)
        self.assertEqual(next(f for f in families if f['id'] == owner_family)['owner_id'], 1)
        self.assertEqual(next(f for f in families if f['id'] == personal['family_id'])['owner_id'], 2)
        switched = self.client.put('/api/family/active', json={'family_id': personal['family_id']})
        self.assertEqual(switched.status_code, 200, switched.text)
        self.assertEqual(switched.json()['role'], 'OWNER')
        self.client.put('/api/family/active', json={'family_id': owner_family})
        self.user_id = 1
        members = self.client.get('/api/family/memberships').json()
        editor = next(m for m in members if m['user_id'] == 2)
        downgraded = self.client.patch(f'/api/family/memberships/{editor["id"]}', json={'role': 'VIEWER'})
        self.assertEqual(downgraded.status_code, 200, downgraded.text)
        self.user_id = 2
        self.assertEqual(self.get_snapshot()['role'], 'VIEWER')
        self.save(self.get_snapshot(), expected=403)
        self.user_id = 1
        removed = self.client.delete(f'/api/family/memberships/{editor["id"]}')
        self.assertEqual(removed.status_code, 200, removed.text)
        self.user_id = 2
        self.assertEqual(self.client.get(f'/api/family/sync?family_id={owner_family}').status_code, 403)
        self.assertEqual(self.get_snapshot()['family_id'], personal['family_id'])
        self.assertEqual(self.client.put('/api/family/active', json={'family_id': owner_family}).status_code, 403)

    def test_removing_membership_clears_only_that_users_family_notifications(self):
        family_id = self.get_snapshot()['family_id']
        with self.factory() as db:
            other_family = Family(owner_id=2, name='编辑者个人家族')
            db.add(other_family)
            db.flush()
            member = FamilyMembership(family_id=family_id, user_id=2, role='EDITOR')
            db.add(member)
            db.get(User, 2).active_family_id = family_id
            removed = [NotificationRecord(user_id=2, family_id=family_id, channel='in_app',
                                          status=status, title='撤销家族消息')
                       for status in ('PENDING', 'SENT')]
            retained = [
                NotificationRecord(user_id=2, family_id=other_family.id, channel='in_app', title='个人家族'),
                NotificationRecord(user_id=2, family_id=None, channel='in_app', title='个人通知'),
                NotificationRecord(user_id=1, family_id=family_id, channel='in_app', title='所有者通知'),
                NotificationRecord(user_id=3, family_id=family_id, channel='in_app', title='另一协作者通知'),
            ]
            db.add_all(removed + retained)
            db.flush()
            db.add_all([WechatDelivery(notification_id=notice.id, user_id=notice.user_id)
                        for notice in removed + retained])
            removed_ids = {notice.id for notice in removed}
            retained_ids = {notice.id for notice in retained}
            membership_id = member.id
            db.commit()
        response = self.client.delete(f'/api/family/memberships/{membership_id}',
                                      params={'family_id': family_id})
        self.assertEqual(response.status_code, 200, response.text)
        with self.factory() as db:
            self.assertIsNone(db.get(FamilyMembership, membership_id))
            self.assertIsNone(db.get(User, 2).active_family_id)
            self.assertEqual(set(db.scalars(select(NotificationRecord.id)).all()), retained_ids)
            self.assertEqual(set(db.scalars(select(WechatDelivery.notification_id)).all()), retained_ids)
            self.assertTrue(removed_ids.isdisjoint(retained_ids))
            self.assertIsNotNone(db.scalar(select(AuditLog).where(AuditLog.action == 'membership.remove')))

    def test_notification_permissions_use_current_membership_and_existing_family(self):
        family_id = self.get_snapshot()['family_id']
        with self.factory() as db:
            membership = FamilyMembership(family_id=family_id, user_id=2, role='VIEWER')
            # 孤立成员资格不能给已删除家族的旧消息恢复投递权限。
            db.add_all([membership, FamilyMembership(family_id=999, user_id=2, role='EDITOR')])
            db.commit()
            owner_notice = NotificationRecord(user_id=1, family_id=family_id, channel='in_app')
            member_notice = NotificationRecord(user_id=2, family_id=family_id, channel='in_app')
            outsider_notice = NotificationRecord(user_id=3, family_id=family_id, channel='in_app')
            missing_notice = NotificationRecord(user_id=2, family_id=999, channel='in_app')
            personal_notice = NotificationRecord(user_id=2, family_id=None, channel='in_app')
            self.assertTrue(can_receive_family_notification(db, owner_notice))
            self.assertTrue(can_receive_family_notification(db, member_notice))
            self.assertFalse(can_receive_family_notification(db, outsider_notice))
            self.assertFalse(can_receive_family_notification(db, missing_notice))
            self.assertTrue(can_receive_family_notification(db, personal_notice))
            # notice 保留原实例，权限仍必须反映数据库最新撤销状态。
            db.delete(membership)
            db.commit()
            self.assertFalse(can_receive_family_notification(db, member_notice))
            self.assertTrue(can_receive_family_notification(db, owner_notice))

    def test_invitation_reject_cancel_expiry_and_duplicate_protection(self):
        family = self.get_snapshot()
        self.assertEqual(self.client.post('/api/family/invitations', json={'invitee': 'notregistered'}).status_code, 404)
        response = self.client.post('/api/family/invitations', json={'invitee': 'editor', 'role': 'VIEWER'})
        invitation = response.json()
        self.assertEqual(self.client.post('/api/family/invitations', json={'invitee': 'editor'}).status_code, 409)
        self.user_id = 2
        response = self.client.post(f'/api/family/invitations/{invitation["id"]}/reject')
        self.assertEqual(response.json()['status'], 'REJECTED')
        self.assertEqual(self.client.post(f'/api/family/invitations/{invitation["id"]}/accept').status_code, 409)
        self.user_id = 1
        invitation = self.client.post('/api/family/invitations', json={'invitee': 'editor'}).json()
        cancelled = self.client.delete(f'/api/family/invitations/{invitation["id"]}')
        self.assertEqual(cancelled.json()['status'], 'CANCELLED')
        invitation = self.client.post('/api/family/invitations', json={'invitee': 'editor'}).json()
        with self.factory() as db:
            db.get(Invitation, invitation['id']).expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.user_id = 2
        self.assertEqual(self.client.post(f'/api/family/invitations/{invitation["id"]}/accept').status_code, 410)
        with self.factory() as db:
            self.assertEqual(db.get(Invitation, invitation['id']).status, 'EXPIRED')

    def test_import_export_are_version_safe_and_preserve_ids(self):
        saved = self.save(self.family_data()).json()
        exported = self.client.get('/api/family/export').json()
        self.assertEqual(exported, saved)
        imported = self.client.post('/api/family/import', json=exported)
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()['members'][0]['id'], saved['members'][0]['id'])
        self.assertEqual(self.client.post('/api/family/import', json=exported).status_code, 409)


class FamilyMigrationTest(unittest.TestCase):
    def test_parent_roles_migration_defaults_legacy_members_and_preserves_explicit_roles(self):
        engine = create_engine('sqlite+pysqlite:///:memory:')
        self.addCleanup(engine.dispose)
        with engine.begin() as db:
            db.execute(text('CREATE TABLE family_members (id INTEGER PRIMARY KEY, family_id INTEGER, '
                            'name VARCHAR(64), client_id VARCHAR(64), parent_ids VARCHAR(512))'))
            db.execute(text("INSERT INTO family_members VALUES "
                            "(11,5,'原母亲','mother','[]'),(12,5,'原子女','child','[11]')"))
        self.assertNotIn('parent_roles', [column['name'] for column in inspect(engine).get_columns('family_members')])
        with patch.object(db_session, 'engine', engine):
            db_session.ensure_schema()
            with engine.begin() as db:
                rows = db.execute(text('SELECT id,name,parent_ids,parent_roles FROM family_members ORDER BY id')).all()
                self.assertEqual(rows, [(11, '原母亲', '[]', '[]'), (12, '原子女', '[11]', '[]')])
                db.execute(text('UPDATE family_members SET parent_roles=:roles WHERE id=12'),
                           {'roles': json.dumps(['mother'])})
            db_session.ensure_schema()
        column = next(column for column in inspect(engine).get_columns('family_members')
                      if column['name'] == 'parent_roles')
        self.assertEqual(str(column['type']).upper(), 'TEXT')
        with engine.connect() as db:
            rows = db.execute(text('SELECT id,name,parent_ids,parent_roles FROM family_members ORDER BY id')).all()
            self.assertEqual(rows, [(11, '原母亲', '[]', '[]'), (12, '原子女', '[11]', '["mother"]')])

    def test_account_and_push_migration_keeps_legacy_sessions_and_notifications(self):
        engine = create_engine('sqlite+pysqlite:///:memory:')
        with engine.begin() as db:
            db.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(32), password_hash VARCHAR(255))'))
            db.execute(text("INSERT INTO users VALUES (1,'原用户','原密码')"))
            db.execute(text('CREATE TABLE push_subscriptions (id INTEGER PRIMARY KEY, user_id INTEGER, endpoint VARCHAR(2048), endpoint_hash VARCHAR(64), p256dh VARCHAR(200), auth VARCHAR(100), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'))
            db.execute(text("INSERT INTO push_subscriptions (id,user_id,endpoint,endpoint_hash,p256dh,auth) VALUES (3,1,'https://fcm.googleapis.com/original','original-hash','key','auth')"))
            db.execute(text('CREATE TABLE notification_records (id INTEGER PRIMARY KEY,user_id INTEGER,reminder_id INTEGER,channel VARCHAR(16),status VARCHAR(16),sent_at DATETIME,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'))
            db.execute(text("INSERT INTO notification_records (id,user_id,channel,status) VALUES (8,1,'in_app','SENT')"))
            db.execute(text('CREATE TABLE user_sessions (id INTEGER PRIMARY KEY,user_id INTEGER,token_hash VARCHAR(128),expires_at DATETIME,revoked_at DATETIME,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)'))
            db.execute(text("INSERT INTO user_sessions (id,user_id,token_hash,expires_at) VALUES (9,1,'legacy-session-hash','2030-01-01')"))
        Base.metadata.create_all(engine)
        with patch.object(db_session, 'engine', engine):
            db_session.ensure_schema()
            db_session.ensure_schema()
        with engine.connect() as db:
            self.assertEqual(db.execute(text('SELECT username,sessions_valid_after FROM users')).first(), ('原用户',None))
            self.assertEqual(db.execute(text('SELECT id,token_hash FROM user_sessions')).first(), (9,'legacy-session-hash'))
            self.assertEqual(db.execute(text('SELECT id,endpoint,session_id,updated_at IS NOT NULL FROM push_subscriptions')).first(), (3,'https://fcm.googleapis.com/original',None,1))
            self.assertEqual(db.execute(text('SELECT id,status,mobile_status,mobile_attempted_at,mobile_error FROM notification_records')).first(), (8,'SENT','DISABLED',None,None))
        self.assertTrue(inspect(engine).has_table('mobile_push_devices'))
        self.assertIn('session_id',[column['name'] for column in inspect(engine).get_columns('mobile_push_devices')])
        self.assertTrue(any(index.get('unique') and index['column_names'] == ['token_hash'] for index in inspect(engine).get_indexes('user_sessions')))
        engine.dispose()

    def test_additive_migration_is_idempotent_and_keeps_legacy_data(self):
        engine = create_engine('sqlite+pysqlite:///:memory:')
        with engine.begin() as db:
            db.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(32), password_hash VARCHAR(255))"))
            db.execute(text("INSERT INTO users VALUES (1, '原账号', '原密码')"))
            db.execute(text("CREATE TABLE families (id INTEGER PRIMARY KEY, owner_id INTEGER, name VARCHAR(64), avatar TEXT)"))
            db.execute(text("INSERT INTO families VALUES (5, 1, '原家族', '')"))
            db.execute(text("CREATE TABLE family_members (id INTEGER PRIMARY KEY, family_id INTEGER, name VARCHAR(64), client_id VARCHAR(64))"))
            db.execute(text("INSERT INTO family_members VALUES (11,5,'原成员',''),(12,5,'另一成员','')"))
            db.execute(text("CREATE TABLE reminders (id INTEGER PRIMARY KEY, family_id INTEGER, title VARCHAR(128))"))
            db.execute(text("INSERT INTO reminders VALUES (18,5,'原提醒')"))
            db.execute(text("CREATE TABLE family_memberships (id INTEGER PRIMARY KEY, family_id INTEGER, user_id INTEGER, role VARCHAR(16), created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"))
        with patch.object(db_session, 'engine', engine):
            db_session.ensure_schema()
            db_session.ensure_schema()
        with engine.connect() as db:
            self.assertEqual(db.execute(text('SELECT username FROM users')).scalar(), '原账号')
            self.assertEqual(db.execute(text('SELECT name,revision FROM families')).first(), ('原家族', 0))
            self.assertEqual(db.execute(text('SELECT id,name,client_id FROM family_members ORDER BY id')).all(), [(11, '原成员', 'member-11'), (12, '另一成员', 'member-12')])
            self.assertEqual(db.execute(text('SELECT title,client_id,calendar FROM reminders')).first(), ('原提醒', 'reminder-18', 'solar'))
            self.assertEqual(db.execute(text('SELECT family_id,user_id,role FROM family_memberships')).all(), [(5,1,'OWNER')])
        self.assertIn('death_date', [column['name'] for column in inspect(engine).get_columns('family_members')])
        engine.dispose()


if __name__ == '__main__':
    unittest.main()
