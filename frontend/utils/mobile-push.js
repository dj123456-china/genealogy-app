import { request } from './api.js'
import { readStorage, writeStorage } from './storage.js'
const deviceKey = session => `family-mobile-push:${session.accountId}`
export async function registerMobilePush(session, valid = () => true) {
  if (typeof plus === 'undefined') return { registered: false, message: '当前平台不是手机 App。' }
  const setting = typeof uni.getAppAuthorizeSetting === 'function' ? uni.getAppAuthorizeSetting() : null
  if (setting?.notificationAuthorized === 'denied') return { registered: false, message: '设备通知权限已关闭，请在系统设置中允许通知。' }
  const configuration = await request('/notifications/delivery-status', { token: session.accessToken })
  if (!valid()) throw Error('账号已切换，请重新授权通知。')
  if (!configuration.mobile_push?.configured) return { registered: false, message: configuration.mobile_push?.message || '服务端尚未配置手机后台推送。' }
  if (typeof uni.getPushClientId !== 'function') return { registered: false, message: '当前 App 未启用 UniPush 模块，请配置后重新打包。' }
  const result = await new Promise((resolve, reject) => uni.getPushClientId({ success: resolve, fail: reject }))
  if (!valid()) throw Error('账号已切换，请重新授权通知。')
  if (!result.cid) throw Error('尚未取得手机推送编号，请检查 App 推送配置。')
  const device = await request('/notifications/mobile-devices', { method: 'POST', token: session.accessToken, data: { client_id: result.cid, platform: plus.os.name === 'iOS' ? 'ios' : 'android' } })
  writeStorage(deviceKey(session), { id: device.id })
  if (!valid()) { await unregisterMobilePush(session); throw Error('账号已切换，请重新授权通知。') }
  return { registered: true, message: '当前手机已登记后台推送；最终接收仍取决于设备权限与网络。' }
}
export async function unregisterMobilePush(session) {
  const saved = readStorage(deviceKey(session))
  if (saved?.id && session.accessToken) {
    try { await request(`/notifications/mobile-devices/${saved.id}`, { method: 'DELETE', token: session.accessToken }) }
    catch (error) { if (error.status !== 404 && error.status !== 401) throw error }
  }
  writeStorage(deviceKey(session), null)
}
