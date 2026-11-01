"""注销与导览迟到写入使用真实SQLite写事务；无真实用户资料。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import tempfile, threading, unittest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from app.api.routes.guides import GuideSettingRequest, save_guide_setting
from app.db.session import Base
from app.models import User, UserGuideSetting
from app.services.accounts import delete_user_data


class GuideLifecycleRaceTest(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+str(Path(self.directory.name)/'guides.sqlite'),
                                  connect_args={'check_same_thread':False,'timeout':20})
        Base.metadata.create_all(self.engine)
        self.factory=sessionmaker(bind=self.engine,expire_on_commit=False,autoflush=False)
        self.add_user()

    def tearDown(self):
        self.engine.dispose();self.directory.cleanup()

    def add_user(self):
        with self.factory() as db:
            db.add(User(id=1,username='race-user',password_hash='test-hash'));db.commit()

    def assert_clean(self):
        with self.factory() as db:
            self.assertIsNone(db.get(User,1))
            self.assertIsNone(db.get(UserGuideSetting,1))

    def test_authenticated_before_deletion_cannot_recreate_settings(self):
        stale=SimpleNamespace(id=1)
        with self.factory() as db:delete_user_data(db,db.get(User,1))
        with self.factory() as db:
            with self.assertRaises(HTTPException) as error:
                save_guide_setting(GuideSettingRequest(dismissal='today'),stale,db)
            self.assertEqual(error.exception.status_code,401)
        self.assert_clean()

    def test_concurrent_save_and_delete_never_leave_orphans_or_server_errors(self):
        for attempt in range(6):
            if attempt:self.add_user()
            barrier=threading.Barrier(2)
            def save():
                with self.factory() as db:
                    barrier.wait(timeout=10)
                    try:
                        return save_guide_setting(GuideSettingRequest(dismissal='permanent'),SimpleNamespace(id=1),db)
                    except HTTPException as error:
                        self.assertEqual(error.status_code,401)
                        return None
            def remove():
                with self.factory() as db:
                    user=db.get(User,1)
                    barrier.wait(timeout=10)
                    delete_user_data(db,user)
            with ThreadPoolExecutor(max_workers=2) as executor:
                saved=executor.submit(save);deleted=executor.submit(remove)
                saved.result(timeout=25);deleted.result(timeout=25)
            self.assert_clean()

    def test_response_is_materialized_before_unlocking_account_at_commit(self):
        with self.factory() as db:
            def delete_after_commit(_):
                with self.factory() as other:delete_user_data(other,other.get(User,1))
            event.listen(db,'after_commit',delete_after_commit,once=True)
            result=save_guide_setting(GuideSettingRequest(dismissal='permanent'),SimpleNamespace(id=1),db)
            self.assertTrue(result.permanently_hidden)
            self.assertFalse(result.show_on_login)
        self.assert_clean()

    def test_user_update_lock_does_not_change_account_timestamp(self):
        with self.factory() as db:
            user=db.get(User,1);timestamp=user.updated_at
            save_guide_setting(GuideSettingRequest(dismissal='today'),user,db)
            db.refresh(user)
            self.assertEqual(user.updated_at,timestamp)
