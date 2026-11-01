import test from 'node:test'
import assert from 'node:assert/strict'
import { effectScope, ref } from 'vue'
import { useLoginForm } from '../utils/login-form.js'
import { AGREEMENT_VERSION } from '../utils/legal.js'

const phone = '13800138000'
const secondPhone = '13900139000'
const registeredAccount = {
  access_token: 'test-token',
  user: { id: 7, username: '已有用户' },
  is_new: false
}

test('默认未勾选条款，账户、手机号和注册提交均不得发送请求', async t => {
  const form = createForm(t, undefined, '', false)
  assert.equal(form.loginForm.acceptedTerms, false)
  form.loginForm.identifier = phone
  t.mock.timers.tick(1000)
  await form.sendLoginSms()
  form.loginForm.smsCode = '012345'
  await form.submitLogin()
  assert.match(form.loginError.value, /阅读并同意/)
  form.loginForm.identifier = '家谱账号'
  form.loginForm.password = 'password1'
  await form.submitLogin()
  form.loginForm.mode = 'register'
  form.loginForm.username = '新用户'
  form.loginForm.phone = phone
  form.loginForm.passwordConfirm = 'password1'
  await form.sendLoginSms()
  await form.submitLogin()
  assert.equal(form.requests.length, 0)
  assert.equal(form.logins.length, 0)
})

test('填写手机号后勾选条款才开始自动验证码，取消勾选会停止尚未发出的验证码', async t => {
  const form = createForm(t, undefined, '', false)
  form.loginForm.identifier = phone
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 0)
  form.loginForm.acceptedTerms = true
  t.mock.timers.tick(499)
  assert.equal(form.requests.length, 0)
  form.loginForm.acceptedTerms = false
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 0)
  form.loginForm.acceptedTerms = true
  t.mock.timers.tick(500)
  await flushPromises()
  assert.equal(form.requests.length, 1)
  assert.deepEqual(form.requests[0].data, { phone, scene: 'login' })
})

test('取消条款同意使已发出的短信响应失效，不覆盖表单或显示过时通知', async t => {
  const form = createForm(t, () => undefined)
  form.loginForm.identifier = phone
  t.mock.timers.tick(500)
  assert.equal(form.smsSending.value, true)
  form.loginForm.acceptedTerms = false
  assert.equal(form.smsSending.value, false)
  form.loginForm.smsCode = '654321'
  form.loginForm.registrationToken = 'verified-proof'
  form.loginError.value = '当前提示'
  form.requests[0].success({ statusCode: 200, data: { message: '验证码已发送' } })
  await flushPromises()
  assert.equal(form.loginForm.smsCode, '654321')
  assert.equal(form.loginForm.registrationToken, 'verified-proof')
  assert.equal(form.loginError.value, '当前提示')
  assert.equal(form.smsCountdown.value, 0)
  assert.equal(form.notifications.length, 0)
  form.loginForm.acceptedTerms = true
  assert.equal(form.smsCountdown.value, 60)
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 1)
})

async function flushPromises() {
  // request、鉴权函数和表单各有一层 Promise，等待整个请求链完成。
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

function createForm(t, reply = () => ({ message: '验证码已发送' }), nextDialog = '', acceptedTerms = true) {
  const previousUni = globalThis.uni
  const requests = [], notifications = [], logins = []
  globalThis.uni = {
    request(options) {
      requests.push(options)
      const response = reply(options, requests.length)
      if (response !== undefined) options.success({ statusCode: 200, data: response })
    }
  }
  t.mock.timers.enable({ apis: ['Date', 'setTimeout', 'setInterval'], now: 1700000000000 })
  const dialog = ref('loginDialog')
  const scope = effectScope()
  const form = scope.run(() => useLoginForm({
    dialog,
    onLogin: async (...args) => { logins.push(args); return {dialog:nextDialog} },
    notify: (...args) => { notifications.push(args) }
  }))
  form.loginForm.acceptedTerms = acceptedTerms
  t.after(() => {
    scope.stop()
    t.mock.timers.reset()
    if (previousUni === undefined) delete globalThis.uni
    else globalThis.uni = previousUni
  })
  return { ...form, dialog, requests, notifications, logins, scope }
}

test('统一输入识别手机号，稳定输入 500 毫秒后自动发送登录验证码', async t => {
  const form = createForm(t)
  form.loginForm.identifier = ` ${phone} `
  assert.equal(form.loginMethod.value, 'phone')
  assert.equal(form.loginForm.phone, phone)
  assert.equal(form.maskedLoginPhone.value, '138****8000')
  t.mock.timers.tick(499)
  assert.equal(form.requests.length, 0)
  t.mock.timers.tick(1)
  await flushPromises()
  assert.equal(form.requests.length, 1)
  assert.equal(form.requests[0].url.endsWith('/auth/send-sms'), true)
  assert.deepEqual(form.requests[0].data, { phone, scene: 'login' })
  assert.equal(form.smsCountdown.value, 60)
  assert.equal(form.smsSending.value, false)
  assert.equal(form.notifications[0][0], '验证码已发送')
})

test('账号输入进入密码登录，不发送短信', async t => {
  const form = createForm(t, () => registeredAccount)
  form.loginForm.identifier = ' 家谱账号 '
  assert.equal(form.loginMethod.value, 'account')
  assert.equal(form.loginForm.phone, '')
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 0)
  form.loginForm.password = 'password1'
  await form.submitLogin()
  assert.equal(form.requests[0].url.endsWith('/auth/login'), true)
  assert.deepEqual(form.requests[0].data, { username: '家谱账号', password: 'password1', accepted_terms_version: AGREEMENT_VERSION })
  assert.equal(form.logins.length, 1)
  assert.equal(form.logins[0][0].username, '已有用户')
  assert.equal(form.dialog.value, '')
  assert.equal(form.loginForm.acceptedTerms, false)
})

test('新手机号验证后直接进入同一窗口的注册步骤，使用一次性凭证完成注册', async t => {
  const form = createForm(t, options => {
    if (options.url.endsWith('/auth/login/sms')) return { requires_registration: true, phone, registration_token: 'registration-proof' }
    return { ...registeredAccount, user: { id: 8, username: '新用户' }, is_new: true }
  })
  form.loginForm.identifier = phone
  form.loginForm.smsCode = '012345'
  await form.submitLogin()
  assert.equal(form.loginForm.mode, 'register')
  assert.equal(form.dialog.value, 'loginDialog')
  assert.equal(form.loginForm.phone, phone)
  assert.equal(form.loginForm.registrationToken, 'registration-proof')
  assert.equal(form.loginForm.acceptedTerms, true)
  assert.equal(form.logins.length, 0)
  assert.deepEqual(form.requests[0].data, { phone, sms_code: '012345', accepted_terms_version: AGREEMENT_VERSION })
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 1)
  form.loginForm.username = '新用户'
  form.loginForm.password = 'password1'
  form.loginForm.passwordConfirm = 'password1'
  await form.submitLogin()
  assert.equal(form.requests[1].url.endsWith('/auth/register'), true)
  assert.deepEqual(form.requests[1].data, { username: '新用户', phone, registration_token: 'registration-proof', password: 'password1', accepted_terms_version: AGREEMENT_VERSION })
  assert.equal(form.logins.length, 1)
  assert.equal(form.logins[0][0].isNew, true)
  assert.equal(form.dialog.value, '')
  assert.equal(form.loginForm.registrationToken, '')
  assert.equal(form.loginForm.acceptedTerms, false)
})

test('已注册手机号用验证码登录并传递记住登录选项', async t => {
  const form = createForm(t, () => registeredAccount)
  form.loginForm.identifier = phone
  form.loginForm.smsCode = '012345'
  form.loginForm.remember = false
  await form.submitLogin()
  assert.equal(form.requests[0].url.endsWith('/auth/login/sms'), true)
  assert.deepEqual(form.requests[0].data, { phone, sms_code: '012345', accepted_terms_version: AGREEMENT_VERSION })
  assert.equal(form.logins.length, 1)
  assert.equal(form.logins[0][0].accessToken, 'test-token')
  assert.equal(form.logins[0][1], false)
  assert.equal(form.dialog.value, '')
  assert.equal(form.loginForm.mode, 'login')
  assert.equal(form.loginForm.identifier, '')
})

test('切换输入清空密码、验证码和凭证，旧短信响应不覆盖新输入', async t => {
  const form = createForm(t, () => undefined)
  form.loginForm.identifier = phone
  t.mock.timers.tick(500)
  assert.equal(form.smsSending.value, true)
  form.loginForm.password = '旧密码'
  form.loginForm.smsCode = '012345'
  form.loginForm.registrationToken = 'old-proof'
  form.loginForm.identifier = '另一个账号'
  assert.equal(form.loginMethod.value, 'account')
  assert.equal(form.loginForm.phone, '')
  assert.equal(form.loginForm.password, '')
  assert.equal(form.loginForm.smsCode, '')
  assert.equal(form.loginForm.registrationToken, '')
  assert.equal(form.smsSending.value, false)
  form.loginForm.password = 'new-password'
  form.loginForm.smsCode = '654321'
  form.loginForm.registrationToken = 'new-proof'
  form.requests[0].success({ statusCode: 200, data: { message: '验证码已发送' } })
  await flushPromises()
  assert.equal(form.loginForm.identifier, '另一个账号')
  assert.equal(form.loginForm.password, 'new-password')
  assert.equal(form.loginForm.smsCode, '654321')
  assert.equal(form.loginForm.registrationToken, 'new-proof')
  assert.equal(form.smsCountdown.value, 0)
  assert.equal(form.notifications.length, 0)
})

test('短信冷却按手机号保存 60 秒，更换号码可发送，原号码冷却到期后可重发', async t => {
  const form = createForm(t)
  form.loginForm.identifier = phone
  await form.sendLoginSms()
  assert.equal(form.smsCountdown.value, 60)
  t.mock.timers.tick(59000)
  assert.equal(form.smsCountdown.value, 1)
  await form.sendLoginSms()
  assert.equal(form.requests.length, 1)
  assert.match(form.loginError.value, /发送太频繁/)
  form.loginForm.identifier = secondPhone
  assert.equal(form.smsCountdown.value, 0)
  t.mock.timers.tick(500)
  await flushPromises()
  assert.equal(form.requests.length, 2)
  assert.deepEqual(form.requests[1].data, { phone: secondPhone, scene: 'login' })
  assert.equal(form.smsCountdown.value, 60)
  form.loginForm.identifier = phone
  assert.equal(form.smsCountdown.value, 1)
  await form.sendLoginSms()
  assert.equal(form.requests.length, 2)
  t.mock.timers.tick(500)
  await form.sendLoginSms()
  assert.equal(form.requests.length, 3)
  assert.deepEqual(form.requests[2].data, { phone, scene: 'login' })
  assert.equal(form.smsCountdown.value, 60)
})

test('忘记密码保留手机号并发送重置场景验证码，重置完成返回统一登录', async t => {
  const form = createForm(t, undefined, '', false)
  form.loginForm.identifier = phone
  form.loginForm.password = 'old-password'
  form.setLoginMode('forgot')
  assert.equal(form.loginForm.mode, 'forgot')
  assert.equal(form.loginForm.phone, phone)
  assert.equal(form.loginForm.password, '')
  t.mock.timers.tick(500)
  assert.equal(form.requests.length, 0)
  await form.sendLoginSms()
  assert.deepEqual(form.requests[0].data, { phone, scene: 'reset_password' })
  form.loginForm.smsCode = '012345'
  form.loginForm.newPassword = 'password2'
  form.loginForm.newPasswordConfirm = 'password2'
  await form.submitLogin()
  assert.equal(form.requests[1].url.endsWith('/auth/forgot-password'), true)
  assert.deepEqual(form.requests[1].data, { phone, sms_code: '012345', new_password: 'password2' })
  assert.equal(form.loginForm.mode, 'login')
  assert.equal(form.loginForm.identifier, '')
  assert.equal(form.dialog.value, 'loginDialog')
  assert.equal(form.logins.length, 0)
  assert.equal(form.loginForm.acceptedTerms, false)
  assert.match(form.loginError.value, /密码已重置/)
})

test('退出忘记密码后恢复统一手机号登录，并清空重置密码和验证码', t => {
  const form = createForm(t)
  form.loginForm.identifier = '家谱账号'
  form.setLoginMode('forgot')
  form.loginForm.phone = phone
  form.loginForm.smsCode = '012345'
  form.loginForm.newPassword = 'password2'
  form.loginForm.newPasswordConfirm = 'password2'
  form.setLoginMode('login')
  assert.equal(form.loginForm.mode, 'login')
  assert.equal(form.loginForm.identifier, phone)
  assert.equal(form.loginMethod.value, 'phone')
  assert.equal(form.loginForm.smsCode, '')
  assert.equal(form.loginForm.newPassword, '')
  assert.equal(form.loginForm.newPasswordConfirm, '')
  assert.equal(form.dialog.value, 'loginDialog')
})

test('关闭窗口或销毁作用域会取消尚未发送的自动验证码', t => {
  const form = createForm(t)
  form.loginForm.identifier = phone
  form.dialog.value = ''
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 0)
  form.dialog.value = 'loginDialog'
  form.scope.stop()
  t.mock.timers.tick(1000)
  assert.equal(form.requests.length, 0)
})

test('手机号登录成功后保留邀请码窗口，并把手机号登录方式传入后续流程',async t=>{
  const form=createForm(t,()=>registeredAccount,'familyGuide')
  form.loginForm.identifier=phone
  form.loginForm.smsCode='012345'
  await form.submitLogin()
  assert.deepEqual(form.logins[0][2],{method:'phone'})
  assert.equal(form.dialog.value,'familyGuide')
  assert.equal(form.loginForm.smsCode,'')
})
