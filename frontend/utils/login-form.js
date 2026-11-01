import { reactive, ref, computed, watch, onScopeDispose } from 'vue'
import { signInOrRegister, loginWithSms, registerWithSms, resetPasswordBySms, sendSms } from './auth.js'
import { AGREEMENT_VERSION } from './legal.js'

const normalize = value => String(value || '').trim().normalize('NFKC')
const isPhone = value => /^1[3-9]\d{9}$/.test(value)

export function useLoginForm({ dialog, initialError = '', onLogin, notify = () => {} }) {
  const loginForm = reactive({ mode: 'login', identifier: '', username: '', phone: '', smsCode: '', registrationToken: '', password: '', passwordConfirm: '', newPassword: '', newPasswordConfirm: '', remember: true, acceptedTerms: false })
  const loginBusy = ref(false), loginError = ref(initialError), smsCountdown = ref(0), smsSending = ref(false)
  const loginIdentifier = computed(() => normalize(loginForm.identifier))
  const loginMethod = computed(() => !loginIdentifier.value ? '' : isPhone(loginIdentifier.value) ? 'phone' : 'account')
  const maskedLoginPhone = computed(() => {
    const phone = normalize(loginForm.phone)
    return isPhone(phone) ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : phone
  })
  const smsCooldowns = new Map()
  let smsTimer, autoSmsTimer, smsRequestId = 0

  function clearAutoSms() { clearTimeout(autoSmsTimer); autoSmsTimer = undefined }
  function invalidateSms() {
    clearAutoSms()
    smsRequestId++
    smsSending.value = false
    loginForm.smsCode = ''
    loginForm.registrationToken = ''
  }
  function refreshSmsCountdown() {
    const now = Date.now()
    for (const [phone, end] of smsCooldowns) if (end <= now) smsCooldowns.delete(phone)
    smsCountdown.value = Math.max(0, Math.ceil(((smsCooldowns.get(normalize(loginForm.phone)) || 0) - now) / 1000))
    if (!smsCountdown.value) { clearInterval(smsTimer); smsTimer = undefined }
    else if (!smsTimer) smsTimer = setInterval(refreshSmsCountdown, 1000)
  }
  function scheduleAutoSms() {
    clearAutoSms()
    if (dialog.value !== 'loginDialog' || loginForm.mode !== 'login' || !loginForm.acceptedTerms || loginMethod.value !== 'phone' || smsCountdown.value || smsSending.value || loginBusy.value) return
    autoSmsTimer = setTimeout(() => { autoSmsTimer = undefined; sendLoginSms() }, 500)
  }
  watch(loginIdentifier, () => {
    if (loginForm.mode !== 'login') return
    invalidateSms()
    loginForm.password = ''
    loginError.value = ''
    loginForm.phone = loginMethod.value === 'phone' ? loginIdentifier.value : ''
    refreshSmsCountdown()
    scheduleAutoSms()
  }, { flush: 'sync' })
  watch(() => normalize(loginForm.phone), () => {
    invalidateSms()
    loginError.value = ''
    refreshSmsCountdown()
  }, { flush: 'sync' })
  watch(() => [dialog.value, loginForm.mode], () => {
    clearAutoSms()
    if (dialog.value !== 'loginDialog') { smsRequestId++; smsSending.value = false; return }
    scheduleAutoSms()
  }, { flush: 'sync' })
  watch(() => loginForm.acceptedTerms, accepted => {
    if (loginForm.mode === 'forgot') return
    if (!accepted) {
      clearAutoSms()
      smsRequestId++
      smsSending.value = false
      return
    }
    loginError.value = ''
    refreshSmsCountdown()
    scheduleAutoSms()
  }, { flush: 'sync' })
  onScopeDispose(() => { clearAutoSms(); clearInterval(smsTimer); smsRequestId++ })

  function resetLoginForm() {
    invalidateSms()
    Object.assign(loginForm, { mode: 'login', identifier: '', username: '', phone: '', smsCode: '', registrationToken: '', password: '', passwordConfirm: '', newPassword: '', newPasswordConfirm: '', acceptedTerms: false })
    refreshSmsCountdown()
  }
  function setLoginMode(mode) {
    if (loginBusy.value || smsSending.value || !['login', 'forgot'].includes(mode) || loginForm.mode === mode) return
    const phone = normalize(loginForm.phone)
    invalidateSms()
    Object.assign(loginForm, { password: '', passwordConfirm: '', newPassword: '', newPasswordConfirm: '', username: '' })
    if (mode === 'login' && phone) loginForm.identifier = phone
    loginForm.mode = mode
    loginForm.phone = mode === 'login' ? (loginMethod.value === 'phone' ? loginIdentifier.value : '') : phone
    loginError.value = ''
    refreshSmsCountdown()
    scheduleAutoSms()
  }
  async function sendLoginSms() {
    clearAutoSms()
    if (loginBusy.value || smsSending.value || dialog.value !== 'loginDialog') return
    if (loginForm.mode !== 'forgot' && !loginForm.acceptedTerms) { loginError.value = '请先阅读并同意《免责声明》和《使用规范》。'; return }
    if (loginForm.mode === 'login' && loginMethod.value !== 'phone') return
    const phone = normalize(loginForm.phone)
    refreshSmsCountdown()
    if (smsCountdown.value) { loginError.value = '发送太频繁，请稍后再试'; return }
    const scene = loginForm.mode === 'forgot' ? 'reset_password' : loginForm.mode === 'register' ? 'register' : 'login'
    const requestId = ++smsRequestId
    smsSending.value = true
    loginError.value = ''
    try {
      await sendSms(phone, scene)
      smsCooldowns.set(phone, Date.now() + 60000)
      if (requestId !== smsRequestId || normalize(loginForm.phone) !== phone) return
      refreshSmsCountdown()
      loginForm.smsCode = ''
      loginForm.registrationToken = ''
      notify('验证码已发送', 'ph-check-circle')
    } catch (error) { if (requestId === smsRequestId) loginError.value = error.message }
    finally { if (requestId === smsRequestId) smsSending.value = false }
  }
  async function submitLogin() {
    if (loginBusy.value || smsSending.value) return
    clearAutoSms()
    if (loginForm.mode !== 'forgot' && !loginForm.acceptedTerms) { loginError.value = '请先阅读并同意《免责声明》和《使用规范》。'; return }
    if (loginForm.mode === 'login' && !loginMethod.value) { loginError.value = '请输入手机号或账号。'; return }
    if (loginForm.mode === 'login' && loginMethod.value === 'phone' && !loginForm.smsCode.trim()) { await sendLoginSms(); return }
    loginError.value = ''; loginBusy.value = true
    try {
      if (loginForm.mode === 'forgot') {
        if (loginForm.newPassword !== loginForm.newPasswordConfirm) throw Error('两次输入的新密码不一致。')
        await resetPasswordBySms(loginForm.phone, loginForm.smsCode, loginForm.newPassword)
        resetLoginForm(); loginError.value = '密码已重置，请使用新密码登录。'; return
      }
      let account
      if (loginForm.mode === 'login' && loginMethod.value === 'phone') {
        const result = await loginWithSms(loginForm.phone, loginForm.smsCode, AGREEMENT_VERSION)
        if (result.requiresRegistration) {
          if (!result.registrationToken) throw Error('手机号验证记录异常，请重新获取验证码。')
          loginForm.phone = result.phone || loginForm.phone
          loginForm.registrationToken = result.registrationToken
          loginForm.mode = 'register'
          loginForm.username = ''; loginForm.password = ''; loginForm.passwordConfirm = ''
          return
        }
        account = result
      } else if (loginForm.mode === 'register') {
        if (loginForm.password !== loginForm.passwordConfirm) throw Error('两次输入的密码不一致。')
        account = await registerWithSms({ username: loginForm.username, phone: loginForm.phone, sms_code: loginForm.smsCode, registration_token: loginForm.registrationToken, password: loginForm.password, accepted_terms_version: AGREEMENT_VERSION })
      } else account = await signInOrRegister(loginIdentifier.value, loginForm.password, AGREEMENT_VERSION)
      const next = await onLogin(account, loginForm.remember, { method: loginForm.mode === 'register' ? 'phone' : loginMethod.value })
      dialog.value = next?.dialog || ''; resetLoginForm()
      notify((account.isNew ? '已注册并登录' : '已登录') + '：' + account.username)
    } catch (error) { loginError.value = error.message }
    finally { loginBusy.value = false }
  }
  return { loginForm, loginMethod, maskedLoginPhone, loginBusy, loginError, smsCountdown, smsSending, resetLoginForm, setLoginMode, sendLoginSms, submitLogin }
}
