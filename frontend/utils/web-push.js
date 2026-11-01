import { request } from './api.js'
import { readStorage, writeStorage } from './storage.js'

let registrationPromise, registrationFlight
const subscriptionKey = session => `family-web-push:${session.accountId}`
function capable() {
  return typeof navigator !== 'undefined' && typeof window !== 'undefined' && window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window
}
function applicationKey(value) {
  const text = atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4))
  return Uint8Array.from(text, c => c.charCodeAt(0))
}
async function registration() {
  if (!registrationPromise) registrationPromise = navigator.serviceWorker.register('/static/family-notification-sw.js').then(async worker => {
    if (worker.active) return worker
    const pending = worker.installing || worker.waiting
    if (!pending) throw Error('后台通知服务未启动。')
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('后台通知服务启动超时。')), 15000)
      const changed = () => {
        if (pending.state === 'activated' || pending.state === 'redundant') {
          clearTimeout(timeout); pending.removeEventListener('statechange', changed)
          pending.state === 'activated' ? resolve() : reject(Error('后台通知服务安装失败。'))
        }
      }
      pending.addEventListener('statechange', changed); changed()
    })
    return worker
  }).catch(error => { registrationPromise = null; throw error })
  return registrationPromise
}
export async function registerWebPush(session, valid = () => true) {
  if (!capable()) return { registered: false, message: '后台通知需要支持推送的 HTTPS 或 localhost 浏览器。' }
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return { registered: false, message: '尚未授予系统通知权限。' }
  if (registrationFlight) await registrationFlight
  registrationFlight = (async () => {
    const configuration = await request('/notifications/delivery-status', { token: session.accessToken })
    if (!valid()) throw Error('账号已切换，请重新授权通知。')
    if (!configuration.web_push?.configured) return { registered: false, message: configuration.web_push?.message || '服务端尚未配置后台推送。' }
    const worker = await registration()
    if (!valid()) throw Error('账号已切换，请重新授权通知。')
    let subscription = await worker.pushManager.getSubscription()
    const expected = applicationKey(configuration.web_push.public_key)
    const oldKey = subscription?.options?.applicationServerKey
    if (oldKey && String(new Uint8Array(oldKey)) !== String(expected)) { await subscription.unsubscribe(); subscription = null }
    if (!subscription) subscription = await worker.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: expected })
    if (!valid()) { await subscription.unsubscribe(); throw Error('账号已切换，请重新授权通知。') }
    const result = await request('/notifications/subscriptions', { method: 'POST', token: session.accessToken, data: subscription.toJSON() })
    writeStorage(subscriptionKey(session), { id: result.id })
    if (!valid()) { await unregisterWebPush(session); throw Error('账号已切换，请重新授权通知。') }
    return { registered: true, message: '当前浏览器已登记后台推送；页面关闭后也能接收通知。' }
  })().finally(() => { registrationFlight = null })
  return registrationFlight
}
export async function unregisterWebPush(session) {
  // 先撤销浏览器订阅，即便断网退出，也停止该设备接收旧账号消息。
  if (capable()) {
    const worker = await navigator.serviceWorker.getRegistration('/static/')
    const subscription = await worker?.pushManager.getSubscription()
    if (subscription) await subscription.unsubscribe()
  }
  const saved = readStorage(subscriptionKey(session))
  if (saved?.id && session.accessToken) {
    try { await request(`/notifications/subscriptions/${saved.id}`, { method: 'DELETE', token: session.accessToken }) }
    catch (error) { if (error.status !== 404 && error.status !== 401) throw error }
  }
  writeStorage(subscriptionKey(session), null)
}
