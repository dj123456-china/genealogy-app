"""邀请码返回快照必须统一读取当前版本；不连接真实MySQL。"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.dialects.mysql import dialect as mysql_dialect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.session import Base
from app.models import Family, FamilyMember, FamilyMembership, InviteCodeRateLimit, Reminder, User
from app.services.family import snapshot
from app.services.invite_codes import (create_code, join_by_code, select_personal_family,
                                      refund_join_attempt, reserve_join_attempt)


class InviteSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite:///:memory:',poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.factory=sessionmaker(bind=self.engine,expire_on_commit=False,autoflush=False)
        with self.factory() as db:
            db.add_all([User(id=1,username='owner',password_hash='hash'),User(id=2,username='viewer',password_hash='hash')])
            db.flush()
            db.add(Family(id=1,owner_id=1,name='before',revision=1))
            db.add_all([FamilyMembership(family_id=1,user_id=1,role='OWNER'),FamilyMembership(family_id=1,user_id=2,role='EDITOR')])
            db.add(FamilyMember(id=1,family_id=1,client_id='old',name='原成员',bio='旧生平'))
            db.add(Reminder(id=1,family_id=1,client_id='old-reminder',title='旧提醒',date='2026-01-01'))
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_current_snapshot_refreshes_cached_family_members_reminders_and_role(self):
        with self.factory() as db:
            family=db.get(Family,1);user=db.get(User,2)
            # 模拟加入事务之前已经读取、缓存了旧对象。
            old_member=db.get(FamilyMember,1);old_reminder=db.get(Reminder,1)
            old_membership=db.scalar(select(FamilyMembership).where(FamilyMembership.user_id==2))
            with self.factory() as other:
                updated=other.get(Family,1);updated.revision=2;updated.name='after'
                other.get(FamilyMember,1).bio='新生平'
                other.get(Reminder,1).title='新提醒'
                other.scalar(select(FamilyMembership).where(FamilyMembership.user_id==2)).role='VIEWER'
                other.add(FamilyMember(family_id=1,client_id='new',name='新增成员'))
                other.commit()
            current=snapshot(db,family,user,current_read=True)
            self.assertEqual((current.revision,current.profile.name,current.role),(2,'after','VIEWER'))
            self.assertEqual([member.name for member in current.members],['原成员','新增成员'])
            self.assertEqual(current.members[0].bio,'新生平')
            self.assertEqual(current.reminders[0].title,'新提醒')
            self.assertEqual(old_membership.role,'VIEWER')
            self.assertEqual(old_member.bio,'新生平')
            self.assertEqual(old_reminder.title,'新提醒')

    def test_mysql_current_snapshot_queries_are_lock_reads(self):
        statements=[]
        def capture(connection,clause,multiparams,params,execution_options):
            if getattr(clause,'is_select',False):
                statements.append(str(clause.compile(dialect=mysql_dialect())))
        with self.factory() as db:
            family=db.get(Family,1);user=db.get(User,2)
            event.listen(self.engine,'before_execute',capture)
            try:snapshot(db,family,user,current_read=True)
            finally:event.remove(self.engine,'before_execute',capture)
        self.assertEqual(len(statements),4)
        self.assertIn('FOR UPDATE',statements[0])
        self.assertTrue(all('LOCK IN SHARE MODE' in sql for sql in statements[1:]))
        self.assertTrue(any('family_memberships' in sql for sql in statements))

    def test_join_and_return_personal_use_current_snapshot(self):
        with self.factory() as db:
            code=create_code(db,db.get(User,1),1,'VIEWER').code
            with patch('app.services.invite_codes.snapshot',wraps=snapshot) as current_snapshot:
                join_by_code(db,db.get(User,2),code,'test')
                self.assertEqual(current_snapshot.call_args.kwargs,{'current_read':True})
                select_personal_family(db,db.get(User,2))
                self.assertEqual(current_snapshot.call_args.kwargs,{'current_read':True})

    def test_success_refund_survives_mysql_seconds_precision_after_window_reset(self):
        now=datetime(2026,10,13,1,2,3,123456)
        with self.factory() as db:
            reserve_join_attempt(db,2,'precision-test')
            db.execute(update(InviteCodeRateLimit).values(window_started_at=now-timedelta(minutes=16)))
            db.commit()
            with patch('app.services.invite_codes.datetime') as clock:
                clock.utcnow.return_value=now
                reserved=reserve_join_attempt(db,2,'precision-test')
            # 模拟默认MySQL DATETIME存储返回值：数据库不保留微秒。
            rows=db.scalars(select(InviteCodeRateLimit)).all()
            for row in rows:row.window_started_at=row.window_started_at.replace(microsecond=0)
            db.commit()
            refund_join_attempt(db,reserved);db.commit()
            self.assertEqual(list(db.scalars(select(InviteCodeRateLimit.attempts))),[0,0])
