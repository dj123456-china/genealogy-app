"""SMS service tests that never contact Alibaba Cloud."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import SmsVerificationRecord
from app.services import sms


PHONE = '13800138000'


def response(*, success=True, model=None, code='OK', message=''):
    return SimpleNamespace(body=SimpleNamespace(success=success, model=model, code=code, message=message))


class FakeClient:
    def __init__(self):
        self.send_calls = []
        self.check_calls = []
        self.send_result = response(model=SimpleNamespace(request_id='provider-trace'))
        self.check_result = response(model=SimpleNamespace(verify_result='PASS'))

    def send_sms_verify_code(self, request):
        self.send_calls.append(request)
        return self.send_result

    def check_sms_verify_code(self, request):
        self.check_calls.append(request)
        return self.check_result


class SmsServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        SmsVerificationRecord.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.client = FakeClient()
        self.client_patch = patch.object(sms, '_client', return_value=self.client)
        self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        self.db.close()
        self.engine.dispose()

    def send(self, scene='register'):
        return sms.send_sms(self.db, PHONE, scene)

    def test_send_uses_sdk_2_request_fields_and_rate_limit(self):
        result = self.send()
        self.assertEqual(result, {'message': '验证码已发送'})
        request = self.client.send_calls[0]
        self.assertEqual(request.template_code, '100001')
        self.assertEqual(request.template_param, '{"code":"##code##","min":"5"}')
        self.assertEqual((request.code_length, request.valid_time, request.interval, request.code_type), (6, 300, 60, 1))
        self.assertRegex(request.out_id, r'^[0-9a-f]{32}$')
        record = self.db.query(SmsVerificationRecord).one()
        self.assertEqual(record.request_id, request.out_id)
        with self.assertRaisesRegex(sms.SmsServiceError, '发送太频繁'):
            self.send('reset_password')
        self.assertEqual(len(self.client.send_calls), 1)

    def test_provider_errors_are_friendly(self):
        self.client.send_result = response(success=False, code='MOBILE_NUMBER_ILLEGAL', message='private provider detail')
        with self.assertRaisesRegex(sms.SmsServiceError, '^手机号格式不正确$'):
            self.send()
        self.client.send_result = response(success=False, code='BUSINESS_LIMIT_CONTROL', message='private provider detail')
        with self.assertRaisesRegex(sms.SmsServiceError, '^发送次数超限，请明天再试$'):
            self.send()
        self.client.send_result = response(success=False, code='biz.FREQUENCY', message='private provider detail')
        with self.assertRaisesRegex(sms.SmsServiceError, '^发送太频繁，请稍后再试$'):
            self.send()
        self.client.send_result = response(success=False, code='SECRET_INTERNAL_ERROR', message='private provider detail')
        with self.assertRaisesRegex(sms.SmsServiceError, '^短信发送失败，请稍后再试$'):
            self.send()
        self.assertEqual(self.db.query(SmsVerificationRecord).count(), 0)

    def test_check_is_scoped_to_scene_and_expires_after_five_minutes(self):
        self.send('register')
        self.assertFalse(sms.check_sms_code(self.db, PHONE, '123456', 'reset_password'))
        self.assertEqual(len(self.client.check_calls), 0)
        record = self.db.query(SmsVerificationRecord).one()
        record.sent_at = datetime.utcnow() - timedelta(seconds=301)
        self.db.commit()
        self.assertFalse(sms.check_sms_code(self.db, PHONE, '123456', 'register'))
        self.assertEqual(len(self.client.check_calls), 0)

    def test_check_rejects_legacy_future_timestamp(self):
        self.send('register')
        record = self.db.query(SmsVerificationRecord).one()
        record.sent_at = datetime.utcnow() + timedelta(hours=8)
        self.db.commit()
        self.assertFalse(sms.check_sms_code(self.db, PHONE, '123456', 'register'))
        self.assertEqual(len(self.client.check_calls), 0)

    def test_check_uses_out_id_and_verifies_only_once(self):
        self.send('register')
        record = self.db.query(SmsVerificationRecord).one()
        self.assertTrue(sms.check_sms_code(self.db, PHONE, '123456', 'register'))
        self.assertEqual(self.client.check_calls[0].out_id, record.request_id)
        self.assertEqual(record.status, 'VERIFIED')
        self.assertIsNotNone(record.verified_at)
        self.assertFalse(sms.check_sms_code(self.db, PHONE, '123456', 'register'))
        self.assertEqual(len(self.client.check_calls), 1)

    def test_check_loses_claim_when_record_changes_during_provider_call(self):
        self.send('register')
        record_id = self.db.query(SmsVerificationRecord).one().id
        original_check = self.client.check_sms_verify_code

        def consumed_by_another_request(request):
            # Simulate a concurrent request claiming the same record while
            # this request is waiting for the provider's response.
            with Session(self.engine) as competing_db:
                competing_db.execute(
                    update(SmsVerificationRecord)
                    .where(SmsVerificationRecord.id == record_id)
                    .values(status='VERIFIED')
                )
                competing_db.commit()
            return original_check(request)

        self.client.check_sms_verify_code = consumed_by_another_request
        self.assertFalse(sms.check_sms_code(self.db, PHONE, '123456', 'register'))
        self.assertEqual(self.db.get(SmsVerificationRecord, record_id).status, 'VERIFIED')

    def test_failed_provider_check_cannot_verify_and_hides_raw_error(self):
        self.send('register')
        self.client.check_result = response(model=SimpleNamespace(verify_result='UNKNOWN'))
        self.assertFalse(sms.check_sms_code(self.db, PHONE, '123456', 'register'))
        self.client.check_result = response(success=False, code='SECRET_INTERNAL_ERROR', message='private provider detail')
        with self.assertRaisesRegex(sms.SmsServiceError, '^验证码校验失败，请稍后再试$'):
            sms.check_sms_code(self.db, PHONE, '123456', 'register')
        self.assertEqual(self.db.query(SmsVerificationRecord).one().status, 'SENT')

    def test_check_accepts_sdk_response_without_optional_success_flag(self):
        self.send('register')
        self.client.check_result = SimpleNamespace(
            body=SimpleNamespace(model=SimpleNamespace(verify_result='PASS'))
        )
        self.assertTrue(sms.check_sms_code(self.db, PHONE, '123456', 'register'))


if __name__ == '__main__':
    unittest.main()
