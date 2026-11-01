import { utf8Bytes } from './encoding.js'
import { pbkdf2Async } from '@noble/hashes/pbkdf2'
import { sha256 } from '@noble/hashes/sha256'
import { bytesToHex, hexToBytes } from '@noble/hashes/utils'
import { readStorage, writeStorage, uid } from './storage.js'
import { request } from './api.js'
const KEY = 'family-local-accounts-v1'
const ITERATIONS = 600000
const SMS_SCENES = new Set(['register', 'login', 'modify_phone', 'reset_password', 'bind_phone', 'verify_phone'])
const normalizeSmsCode = value => String(value || '').trim().normalize('NFKC')
export function readAccounts() {
  const accounts = readStorage(KEY, [])
  if (!Array.isArray(accounts) || accounts.some(a => !a || typeof a.username !== 'string' || !/^[a-f0-9]{32}$/.test(a.id) || a.version !== 1 || a.iterations !== ITERATIONS || !/^[a-f0-9]{32}$/.test(a.salt) || !/^[a-f0-9]{64}$/.test(a.passwordHash))) throw new Error('本机账号记录异常，请保留数据并检查存储。')
  return accounts
}
export function matchesSession(session) {
  if (session?.authVersion === 2 && session.accessToken && session.accountId && session.username) return true
  return !!session && session.authVersion === 1 && readAccounts().some(a => a.id === session.accountId && a.username === session.username)
}
function validateCredentials(username, password) {
  if (!username || username.length > 32 || /[\u0000-\u001f\u007f]/.test(username)) throw new Error('请输入 1 至 32 个字符的登录名。')
  if (typeof password !== 'string' || password.length < 6 || password.length > 64 || !password.trim()) throw new Error('密码须为 6 至 64 位，且不能全为空格。')
}
function validatePassword(password) {
  if (typeof password !== 'string' || password.length < 6 || password.length > 64 || !password.trim()) throw new Error('密码须为 6 至 64 位，且不能全为空格。')
}
function normalizeRemoteAccount(result) { return { username: result.user.username, accountId: String(result.user.id), user: result.user, accessToken: result.access_token, tokenType: result.token_type || 'bearer', authVersion: 2, isNew: !!result.is_new } }
export async function verifyLegacyLocalAccount(rawName, password) {
  const username = String(rawName || '').trim().normalize('NFKC')
  validateCredentials(username, password)
  const account = readAccounts().find(a => a.username.toLowerCase() === username.toLowerCase())
  if (!account) throw Error('此设备未找到该旧本机账号，请回到原设备导出备份。')
  const hash = bytesToHex(await pbkdf2Async(sha256, utf8Bytes(password), hexToBytes(account.salt), { c: ITERATIONS, dkLen: 32, asyncTick: 12 }))
  let mismatch = 0
  for (let i = 0; i < hash.length; i++) mismatch |= hash.charCodeAt(i) ^ account.passwordHash.charCodeAt(i)
  if (mismatch) throw Error('旧本机账号密码不正确。')
  return { username: account.username, accountId: account.id, authVersion: 1 }
}
export async function signInOrRegister(rawName, password, acceptedTermsVersion) {
  const username = String(rawName || '').trim().normalize('NFKC'); validateCredentials(username, password)
  if (typeof uni.request === 'function') return normalizeRemoteAccount(await request('/auth/login', { method: 'POST', data: { username, password, accepted_terms_version: acceptedTermsVersion } }))
  const accounts = readAccounts(), existing = accounts.find(a => a.username.toLowerCase() === username.toLowerCase()), salt = existing ? existing.salt : uid()
  const hash = bytesToHex(await pbkdf2Async(sha256, utf8Bytes(password), hexToBytes(salt), { c: ITERATIONS, dkLen: 32, asyncTick: 12 }))
  if (existing) { let mismatch = 0; for (let i = 0; i < hash.length; i++) mismatch |= hash.charCodeAt(i) ^ existing.passwordHash.charCodeAt(i); if (mismatch) throw new Error('密码不正确，请重新输入。') }
  const account = existing || { id: uid(), username, version: 1, salt, passwordHash: hash, iterations: ITERATIONS, createdAt: Date.now() }
  if (!existing) writeStorage(KEY, [...accounts, account])
  return { username: account.username, accountId: account.id, authVersion: 1, isNew: !existing }
}
export async function sendSms(phone, scene) {
  const value = String(phone || '').trim().normalize('NFKC')
  const normalizedScene = String(scene || '').trim().normalize('NFKC')
  if (!/^1[3-9]\d{9}$/.test(value)) throw new Error('请输入有效的中国大陆 11 位手机号。')
  if (!SMS_SCENES.has(normalizedScene)) throw new Error('短信场景不支持。')
  return request('/auth/send-sms', { method: 'POST', data: { phone: value, scene: normalizedScene } })
}
export async function loginWithSms(rawPhone, rawCode, acceptedTermsVersion) {
  const phone = String(rawPhone || '').trim().normalize('NFKC')
  const sms_code = normalizeSmsCode(rawCode)
  if (!/^1[3-9]\d{9}$/.test(phone)) throw new Error('请输入有效的中国大陆 11 位手机号。')
  if (!/^\d{6}$/.test(sms_code)) throw new Error('请输入 6 位短信验证码。')
  if (typeof uni.request !== 'function') throw new Error('短信登录需要连接后端，请稍后重试。')
  const result = await request('/auth/login/sms', { method: 'POST', data: { phone, sms_code, accepted_terms_version: acceptedTermsVersion } })
  if (result?.requires_registration || (result?.is_new && !result?.access_token)) {
    return {
      isNew: true,
      requiresRegistration: true,
      phone: result.phone || phone,
      registrationToken: result.registration_token || ''
    }
  }
  return normalizeRemoteAccount(result)
}

export async function registerWithSms(data) {
  const username = String(data?.username || '').trim().normalize('NFKC')
  const phone = String(data?.phone || '').trim().normalize('NFKC')
  const smsCode = normalizeSmsCode(data?.sms_code)
  const registrationToken = String(data?.registration_token || '').trim()
  validateCredentials(username, data?.password)
  if (/^1[3-9]\d{9}$/.test(username)) throw new Error('账号不能使用手机号格式，请换一个登录名。')
  if (!/^1[3-9]\d{9}$/.test(phone)) throw new Error('请输入有效的中国大陆 11 位手机号。')
  if (!registrationToken && !/^\d{6}$/.test(smsCode)) throw new Error('请输入 6 位短信验证码。')
  if (typeof uni.request === 'function') return normalizeRemoteAccount(await request('/auth/register', { method: 'POST', data: { username, phone, ...(registrationToken ? { registration_token: registrationToken } : { sms_code: smsCode }), password: data.password, accepted_terms_version: data.accepted_terms_version } }))
  throw new Error('当前离线模式不支持短信注册，请连接后端。')
}
export async function resetPasswordBySms(phone, code, newPassword) {
  const value = String(phone || '').trim().normalize('NFKC')
  const smsCode = normalizeSmsCode(code)
  if (!/^1[3-9]\d{9}$/.test(value)) throw new Error('请输入有效的中国大陆 11 位手机号。')
  validatePassword(newPassword)
  if (!/^\d{6}$/.test(smsCode)) throw new Error('请输入 6 位短信验证码。')
  return request('/auth/forgot-password', { method: 'POST', data: { phone: value, sms_code: smsCode, new_password: newPassword } })
}
// 兼容旧版本地数据测试；新页面不提供手机号入口。
export async function signInWithPhone(rawPhone, password, acceptedTermsVersion) {
  const phone = String(rawPhone || '').trim().normalize('NFKC')
  if (!/^1[3-9]\d{9}$/.test(phone)) throw new Error('请输入有效的中国大陆 11 位手机号。')
  validateCredentials(phone, password)
  if (typeof uni.request === 'function') return normalizeRemoteAccount(await request('/auth/login', { method: 'POST', data: { phone, password, accepted_terms_version: acceptedTermsVersion } }))
  return signInOrRegister(phone, password, acceptedTermsVersion)
}
