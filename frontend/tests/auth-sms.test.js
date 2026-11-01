import test from 'node:test'
import assert from 'node:assert/strict'
import { signInOrRegister, signInWithPhone, loginWithSms, registerWithSms, resetPasswordBySms, sendSms } from '../utils/auth.js'
import { AGREEMENT_VERSION } from '../utils/legal.js'

const phone = '13800138000'
const tokenResponse = {
  access_token: 'test-token',
  user: { id: 1, username: '测试用户' },
  is_new: true
}

function mockRequests(reply = tokenResponse) {
  const calls = []
  globalThis.uni = {
    request(options) {
      calls.push(options)
      options.success({ statusCode: 200, data: reply })
    }
  }
  return calls
}

test('注册可使用已验证的一次性凭证，且不发送空验证码字段', async () => {
  const calls = mockRequests()
  const account = await registerWithSms({ username: '测试用户', phone, password: 'password1', registration_token: 'registration-proof', accepted_terms_version: AGREEMENT_VERSION })
  assert.equal(account.username, '测试用户')
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url.endsWith('/auth/register'), true)
  assert.deepEqual(calls[0].data, { username: '测试用户', phone, registration_token: 'registration-proof', password: 'password1', accepted_terms_version: AGREEMENT_VERSION })
})

test('直接注册必须提供六位数字验证码', async () => {
  const calls = mockRequests()
  await assert.rejects(registerWithSms({ username: '测试用户', phone, password: 'password1', sms_code: '1234' }), /6 位短信验证码/)
  assert.equal(calls.length, 0)
  await registerWithSms({ username: '测试用户', phone, password: 'password1', sms_code: '012345', accepted_terms_version: AGREEMENT_VERSION })
  assert.equal(calls[0].data.sms_code, '012345')
  assert.equal('registration_token' in calls[0].data, false)
})

test('短信验证码会规范化全角数字后再提交', async () => {
  const calls = mockRequests()
  const result = await loginWithSms(phone, '１２３４５６', AGREEMENT_VERSION)
  assert.equal(result.username, '测试用户')
  assert.equal(calls[0].data.sms_code, '123456')
  assert.equal(calls[0].data.accepted_terms_version, AGREEMENT_VERSION)
})

test('发送验证码拒绝不支持的场景且不发请求', async () => {
  const calls = mockRequests()
  await assert.rejects(sendSms(phone, 'unknown_scene'), /短信场景不支持/)
  assert.equal(calls.length, 0)
})

test('重置密码和发送验证码使用正确接口与场景', async () => {
  const calls = mockRequests({ message: '验证码已发送' })
  await sendSms(phone, 'reset_password')
  assert.equal(calls[0].url.endsWith('/auth/send-sms'), true)
  assert.deepEqual(calls[0].data, { phone, scene: 'reset_password' })
  await resetPasswordBySms(phone, '012345', 'password2')
  assert.equal(calls[1].url.endsWith('/auth/forgot-password'), true)
  assert.deepEqual(calls[1].data, { phone, sms_code: '012345', new_password: 'password2' })
})

test('发送验证码时保留底层网络错误，便于定位连接失败原因', async () => {
  globalThis.uni = {
    request(options) {
      options.fail({ errMsg: 'request:fail connection refused' })
    }
  }
  await assert.rejects(sendSms(phone, 'login'), /connection refused/)
})

test('短信登录的新手机号交接注册凭证', async () => {
  const calls = mockRequests({ requires_registration: true, phone, registration_token: 'registration-proof' })
  const result = await loginWithSms(phone, '012345', AGREEMENT_VERSION)
  assert.equal(result.requiresRegistration, true)
  assert.equal(result.registrationToken, 'registration-proof')
  assert.equal(calls[0].url.endsWith('/auth/login/sms'), true)
  assert.deepEqual(calls[0].data, { phone, sms_code: '012345', accepted_terms_version: AGREEMENT_VERSION })
})

test('所有云端登录入口提交调用者明确传入的同意版本，不自动补充同意', async () => {
  const calls = mockRequests()
  await signInOrRegister('测试用户', 'password1', AGREEMENT_VERSION)
  await signInWithPhone(phone, 'password1', AGREEMENT_VERSION)
  assert.deepEqual(calls[0].data, { username: '测试用户', password: 'password1', accepted_terms_version: AGREEMENT_VERSION })
  assert.deepEqual(calls[1].data, { phone, password: 'password1', accepted_terms_version: AGREEMENT_VERSION })
  await loginWithSms(phone, '012345')
  assert.equal(calls[2].data.accepted_terms_version, undefined)
})
