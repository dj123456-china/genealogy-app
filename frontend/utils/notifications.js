import { store, authenticatedRequest } from './store.js'
import { readStorage, writeStorage } from './storage.js'
import { registerWebPush, unregisterWebPush } from './web-push.js'
import { registerMobilePush, unregisterMobilePush } from './mobile-push.js'
import { registerWechatPush, unregisterWechatPush } from './wechat-push.js'
let timer
let registeredSession = '', registering = false
let nativeClickRegistered = false
const sessionCurrent = session => () => !!session?.accessToken && store.session?.accountId === session.accountId && store.session?.accessToken === session.accessToken
const receivedKey = () => `family-notification-delivered:${store.session?.accountId}`
export async function requestSystemNotificationPermission() {
  const session = store.session, valid = sessionCurrent(session)
  if (!valid()) return { granted: false, message: '请先登录服务端账号。' }
  // #ifdef MP-WEIXIN
  if (typeof wx !== 'undefined') {
  try { const result = await registerWechatPush(session, valid); return { granted: result.registered, message: result.message } }
  catch (error) { return { granted: false, message: error.message || '微信授权登记失败。' } }
  }
  // #endif
  // #ifdef H5
  if (typeof Notification !== 'undefined') {
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return { granted: false, message: '浏览器未授予系统通知权限，应用内通知仍可查看。' }
    try {
      if (!valid()) throw Error('账号已切换，请重新授权通知。')
      const result = await registerWebPush(session, valid)
      registeredSession = result.registered ? store.session?.accessToken || '' : ''
      return { granted: true, message: result.message }
    } catch (error) { return { granted: true, message: `前台通知已授权；后台登记失败：${error.message}` } }
  }
  // #endif
  // #ifndef H5
  if (typeof plus !== 'undefined') {
    const setting = typeof uni.getAppAuthorizeSetting === 'function' ? uni.getAppAuthorizeSetting() : null
    if (setting?.notificationAuthorized === 'denied') {
      if (typeof uni.openAppAuthorizeSetting === 'function') uni.openAppAuthorizeSetting({})
      return { granted: false, message: '请在系统设置中允许通知后重新登记设备。' }
    }
    try { const result = await registerMobilePush(session, valid); return { granted: result.registered, message: result.message } }
    catch (error) { return { granted: false, message: error.message || '手机通知登记失败。' } }
  }
  // #endif
  return { granted: false, message: '当前平台不支持直接系统通知，请查看应用内通知。' }
}
async function showSystemNotification(item) {
  // #ifdef H5
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    new Notification(item.title, { body: item.body, tag: `jiapu-${item.id}` })
    return true
  }
  // #endif
  // #ifndef H5
  if (typeof plus !== 'undefined' && plus.push) {
    plus.push.createMessage(item.body, JSON.stringify({ notificationId: item.id }), { title: item.title, cover: false })
    return true
  }
  // #endif
  return false
}
export async function refreshNotifications() {
  const session = store.session
  if (!session?.accessToken || store.guest) { store.notifications = []; return [] }
  const rows = await authenticatedRequest('/notifications')
  if (store.session?.accountId !== session.accountId || store.session?.accessToken !== session.accessToken) return []
  store.notifications = Array.isArray(rows) ? rows : rows.items || []
  if (!registering && store.user?.system_notifications_enabled && store.user?.notifications_enabled && typeof Notification !== 'undefined' && Notification.permission === 'granted' && registeredSession !== session.accessToken) {
    registering = true
    try { const result = await registerWebPush(session, sessionCurrent(session)); if (result.registered && store.session?.accessToken === session.accessToken) registeredSession = session.accessToken }
    catch { /* 登记失败仍允许阅读收件箱，下次刷新重试。 */ }
    finally { registering = false }
  }
  // #ifdef H5
  if (!store.user?.system_notifications_enabled && registeredSession) { await unregisterWebPush(session).catch(() => {}); registeredSession = '' }
  // #endif
  // #ifdef MP-WEIXIN
  if (!store.user?.system_notifications_enabled) await unregisterWechatPush(session).catch(() => {})
  // #endif
  // #ifdef APP-PLUS
  if (!registering && store.user?.system_notifications_enabled && store.user?.notifications_enabled && registeredSession !== session.accessToken) {
    registering = true
    try { const result = await registerMobilePush(session, sessionCurrent(session)); if (result.registered && store.session?.accessToken === session.accessToken) registeredSession = session.accessToken }
    catch { /* 通道状态中保留未配置/登记失败状态。 */ }
    finally { registering = false }
  }
  if (!store.user?.system_notifications_enabled && registeredSession) { await unregisterMobilePush(session).catch(() => {}); registeredSession = '' }
  // #endif
  if (store.user?.notifications_enabled && store.user?.system_notifications_enabled) {
    const delivered = new Set(readStorage(receivedKey(), []))
    for (const item of store.notifications) {
      if (!item.read_at && !delivered.has(String(item.id))) {
        // 同一条后台已投递消息不再被页面重复弹出。
        if (item.push_status === 'SENT' || item.push_status === 'PARTIAL' || item.mobile_status === 'ACCEPTED' || item.mobile_status === 'PARTIAL' || await showSystemNotification(item)) delivered.add(String(item.id))
      }
    }
    writeStorage(receivedKey(), [...delivered].slice(-500))
  }
  return store.notifications
}
export async function markNotificationRead(id) { await authenticatedRequest(`/notifications/${id}/read`, { method: 'PATCH' }); return refreshNotifications() }
export async function markAllNotificationsRead() { await authenticatedRequest('/notifications/read-all', { method: 'POST' }); return refreshNotifications() }
export function startNotificationWatcher() {
  if (timer) return
  // #ifdef APP-PLUS
  if (!nativeClickRegistered) {
    nativeClickRegistered = true
    if (typeof uni.onPushMessage === 'function') uni.onPushMessage(event => { if (event.type === 'click') uni.$emit('family-open-notifications') })
    else if (typeof plus !== 'undefined' && plus.push) plus.push.addEventListener('click', () => uni.$emit('family-open-notifications'))
  }
  // #endif
  timer = setInterval(() => { if (store.session?.accessToken) refreshNotifications().catch(() => {}) }, 30000)
  refreshNotifications().catch(() => {})
}
export function stopNotificationWatcher() { clearInterval(timer); timer = null }
