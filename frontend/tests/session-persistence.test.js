import test from 'node:test'
import assert from 'node:assert/strict'

const PERSISTENT_KEY = 'family-auth-user'
const TEMPORARY_KEY = 'family-auth-session'
const account = () => ({ authVersion: 2, accountId: '7', username: '江先生', accessToken: 'device-token', user: { id: 7, username: '江先生', active_family_id: 12 } })
const family = () => ({ family_id: 12, revision: 1, role: 'OWNER', profile: { name: '江氏家族', avatar: '' }, members: [], reminders: [] })
let loadNumber = 0
const loadStore = () => import(`../utils/store.js?session-persistence=${++loadNumber}`)

function mockDevice(handler) {
  const local = new Map(), temporary = new Map(), calls = []
  globalThis.sessionStorage = {
    getItem: key => temporary.get(key) ?? null,
    setItem: (key, value) => temporary.set(key, String(value)),
    removeItem: key => temporary.delete(key)
  }
  globalThis.uni = {
    getStorageSync: key => local.get(key) ?? '',
    setStorageSync: (key, value) => local.set(key, JSON.parse(JSON.stringify(value))),
    removeStorageSync: key => local.delete(key),
    request: options => { calls.push(options); (handler || authenticatedServer)(options) }
  }
  return { local, temporary, calls }
}
const ok = (options, data) => options.success({ statusCode: 200, data })
function authenticatedServer(options) {
  const path = new URL(options.url).pathname
  if (path.endsWith('/auth/me')) return ok(options, account().user)
  if (path.endsWith('/family/list')) return ok(options, [{ id: 12, owner_id: 7, role: 'OWNER', active: true }])
  if (path.endsWith('/family/sync')) return ok(options, family())
  if (path.endsWith('/auth/logout')) return ok(options, { success: true })
  assert.fail(`保持登录不应调用其他接口：${path}`)
}

test('默认登录保存同设备凭证，并标记为持久登录', async () => {
  const { local, temporary } = mockDevice()
  const { store, activateSession } = await loadStore()
  await activateSession(account())
  assert.equal(local.get(PERSISTENT_KEY).accessToken, 'device-token')
  assert.equal(local.get(PERSISTENT_KEY).storage, 'local')
  assert.equal(store.session.storage, 'local')
  assert.equal(store.sessionValidated, true)
  assert.equal(temporary.has(TEMPORARY_KEY), false)
})

test('关闭保持登录只保存当前网页会话，刷新后仍不升级为持久登录', async () => {
  const { local, temporary } = mockDevice()
  const first = await loadStore()
  await first.activateSession(account(), false)
  assert.equal(local.has(PERSISTENT_KEY), false)
  assert.equal(JSON.parse(temporary.get(TEMPORARY_KEY)).storage, 'session')

  const refreshed = await loadStore()
  await refreshed.restoreSession()
  assert.equal(refreshed.store.session.accountId, '7')
  assert.equal(refreshed.store.sessionValidated, true)
  assert.equal(refreshed.store.session.storage, 'session')
  assert.equal(local.has(PERSISTENT_KEY), false)

  temporary.clear() // 关闭网页后，新网页会话无法恢复临时登录。
  const reopened = await loadStore()
  await reopened.restoreSession()
  assert.equal(reopened.store.session, null)
  assert.equal(reopened.store.sessionRestoring, false)
})

test('同设备重新打开自动恢复服务端账号，无需密码或短信验证码', async () => {
  const { local, temporary, calls } = mockDevice()
  const first = await loadStore()
  await first.activateSession(account())
  temporary.clear()
  calls.length = 0

  const reopened = await loadStore()
  assert.equal(reopened.store.sessionRestoring, true)
  assert.equal(reopened.store.session, null)
  await reopened.restoreSession()
  assert.equal(reopened.store.sessionRestoring, false)
  assert.equal(reopened.store.session.accountId, '7')
  assert.equal(reopened.store.user.id, 7)
  assert.equal(reopened.store.sessionValidated, true)
  assert.equal(reopened.store.familyId, 12)
  assert.equal(local.get(PERSISTENT_KEY).storage, 'local')
  assert.ok(calls.some(options => options.url.endsWith('/auth/me')))
  assert.ok(calls.every(options => options.method === 'GET'))
  assert.ok(calls.every(options => options.header.Authorization === 'Bearer device-token'))
})

test('启动恢复结束前保留恢复标志，没有本机登录也会结束恢复', async () => {
  const { local } = mockDevice()
  const empty = await loadStore()
  assert.equal(empty.store.sessionRestoring, true)
  await empty.restoreSession()
  assert.equal(empty.store.sessionRestoring, false)
  assert.equal(empty.store.session, null)

  let held
  globalThis.uni.request = options => {
    if (options.url.endsWith('/auth/me')) { held = options; return }
    authenticatedServer(options)
  }
  local.set(PERSISTENT_KEY, { ...account(), storage: 'local' })
  const saved = await loadStore()
  const restoring = saved.restoreSession()
  assert.ok(held)
  assert.equal(saved.store.sessionRestoring, true)
  ok(held, account().user)
  await restoring
  assert.equal(saved.store.sessionRestoring, false)
})

test('主动退出清除持久和临时凭证，重新打开不能恢复登录', async () => {
  const { local, temporary, calls } = mockDevice()
  const first = await loadStore()
  await first.activateSession(account())
  temporary.set(TEMPORARY_KEY, JSON.stringify({ ...account(), storage: 'session' }))
  await first.logout()
  assert.equal(first.store.session, null)
  assert.equal(local.has(PERSISTENT_KEY), false)
  assert.equal(temporary.has(TEMPORARY_KEY), false)
  assert.ok(calls.some(options => options.url.endsWith('/auth/logout') && options.method === 'POST'))

  calls.length = 0
  const reopened = await loadStore()
  await reopened.restoreSession()
  assert.equal(reopened.store.session, null)
  assert.equal(reopened.store.sessionRestoring, false)
  assert.equal(calls.length, 0)
})

test('恢复时服务端确认凭证过期或撤销，清除全部登录凭证', async () => {
  const { local, temporary } = mockDevice(options => options.success({ statusCode: 401, data: { detail: '登录已过期或已撤销' } }))
  local.set(PERSISTENT_KEY, { ...account(), storage: 'local' })
  temporary.set(TEMPORARY_KEY, JSON.stringify({ ...account(), storage: 'session' }))
  const { store, restoreSession } = await loadStore()
  await restoreSession()
  assert.equal(store.session, null)
  assert.equal(store.sessionValidated, false)
  assert.equal(store.sessionRestoring, false)
  assert.equal(local.has(PERSISTENT_KEY), false)
  assert.equal(temporary.has(TEMPORARY_KEY), false)
})

test('网络暂不可用仍保留同设备会话，联网后可继续自动恢复', async () => {
  const { local } = mockDevice(options => options.fail())
  local.set(PERSISTENT_KEY, { ...account(), storage: 'local' })
  const offline = await loadStore()
  await offline.restoreSession()
  assert.equal(offline.store.session.accountId, '7')
  assert.equal(offline.store.sessionValidated, false)
  assert.equal(offline.store.sessionRestoring, false)
  assert.equal(offline.store.syncStatus, 'pending')
  assert.equal(local.get(PERSISTENT_KEY).accessToken, 'device-token')

  globalThis.uni.request = authenticatedServer
  const online = await loadStore()
  await online.restoreSession()
  assert.equal(online.store.session.accountId, '7')
  assert.equal(online.store.sessionValidated, true)
  assert.equal(online.store.syncStatus, 'synced')
})

test('恢复账号后同步接口确认会话失效，也会清除同设备登录凭证', async () => {
  const { local } = mockDevice(options => {
    if (options.url.includes('/family/sync')) return options.success({ statusCode: 401, data: { detail: '会话已撤销' } })
    authenticatedServer(options)
  })
  local.set(PERSISTENT_KEY, { ...account(), storage: 'local' })
  const { store, restoreSession } = await loadStore()
  await restoreSession()
  assert.equal(store.session, null)
  assert.equal(store.sessionRestoring, false)
  assert.equal(local.has(PERSISTENT_KEY), false)
  assert.equal(store.error, '会话已撤销')
})

test('旧会话的迟到失效响应不会清除新登录的同设备凭证', async () => {
  let held
  const { local } = mockDevice(options => {
    if (options.url.endsWith('/auth/me') && options.header.Authorization === 'Bearer device-token') { held = options; return }
    authenticatedServer(options)
  })
  local.set(PERSISTENT_KEY, { ...account(), storage: 'local' })
  const { store, restoreSession, activateSession } = await loadStore()
  const restoring = restoreSession()
  assert.ok(held)
  await activateSession({ ...account(), accessToken: 'new-device-token' })
  held.success({ statusCode: 401, data: { detail: '旧会话已失效' } })
  await restoring
  assert.equal(store.session.accessToken, 'new-device-token')
  assert.equal(store.sessionValidated, true)
  assert.equal(local.get(PERSISTENT_KEY).accessToken, 'new-device-token')
  assert.equal(store.error, '')
})
