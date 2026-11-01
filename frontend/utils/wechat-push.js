import { request } from './api.js'
import { readStorage, writeStorage } from './storage.js'
const key = session => `family-wechat-push:${session.accountId}`
export async function registerWechatPush(session, valid = () => true) {
  const status = await request('/notifications/delivery-status', { token: session.accessToken })
  if (!valid()) throw Error('账号已切换，请重新授权通知。')
  const channel = status.wechat_push
  if (!channel?.configured) return { registered: false, message: channel?.message || '服务端尚未配置微信订阅消息。' }
  if (typeof uni.requestSubscribeMessage !== 'function') return { registered: false, message: '当前平台不支持微信订阅消息。' }
  const permission = await new Promise((resolve, reject) => uni.requestSubscribeMessage({ tmplIds: [channel.template_id], success: resolve, fail: reject }))
  if (permission[channel.template_id] !== 'accept') return { registered: false, message: '未授予微信订阅消息权限，站内通知仍可查看。' }
  const login = await new Promise((resolve, reject) => uni.login({ provider: 'weixin', success: resolve, fail: reject }))
  if (!valid()) throw Error('账号已切换，请重新授权通知。')
  if (!login.code) throw Error('未取得微信设备凭证，请重新授权。')
  const device = await request('/notifications/wechat-devices', { method: 'POST', token: session.accessToken, data: { code: login.code } })
  writeStorage(key(session), { id: device.id })
  if (!valid()) { await unregisterWechatPush(session); throw Error('账号已切换，请重新授权通知。') }
  return { registered: true, message: device.message }
}
export async function unregisterWechatPush(session) {
  const saved = readStorage(key(session))
  if (saved?.id && session.accessToken) {
    try { await request(`/notifications/wechat-devices/${saved.id}`, { method: 'DELETE', token: session.accessToken }) }
    catch (error) { if (error.status !== 404 && error.status !== 401) throw error }
  }
  writeStorage(key(session), null)
}
