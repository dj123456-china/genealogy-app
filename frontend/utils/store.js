import { reactive } from 'vue'
import { readStorage, writeStorage, uid } from './storage.js'
import { matchesSession, verifyLegacyLocalAccount } from './auth.js'
import { generationFor, validateMember, parentLinks } from './family.js'
import { dateString, parseDate, lunarDate, reminderCalendarFields } from './dates.js'
import { request } from './api.js'
import { clone, mergeFamily, sameFamily } from './sync.js'
import { clearAvatarCache, resolveAvatar, readAvatarPayload, persistAvatar } from './avatar.js'
import { unregisterWebPush } from './web-push.js'
import { unregisterMobilePush } from './mobile-push.js'
import { unregisterWechatPush } from './wechat-push.js'

const SESSION_KEY = 'family-auth-user'
const emptyData = () => ({ members: [], reminders: [], profile: { name: '我的家谱', avatar: '' } })
export const store = reactive({ ...emptyData(), session: null, sessionRestoring: true, guest: false, user: null, error: '', syncStatus: 'idle', revision: 0, familyId: null, role: 'OWNER', sessionValidated: false, notifications: [], conflicts: [], syncConflict: null, editing: false, permissionLost: false, importRecoveryAvailable: false })
let epoch = 0, context = null, timer = null
const cacheKey = (accountId, familyId) => `jiapu-data-v4:${accountId}:${familyId || 'local'}`
const activeKey = id => `family-active-v4:${id}`
const current = ctx => context === ctx && epoch === ctx.epoch && store.session?.accountId === ctx.accountId && store.familyId === ctx.familyId
function snapshot() { return clone({ profile: store.profile, members: store.members, reminders: store.reminders }) }
function mergeChecked(base, local, remote) {
  const merged = mergeFamily(base, local, remote)
  try {
    merged.data.members.forEach(m => validateMember(m, merged.data.members, dateString()))
    const ids = new Set(merged.data.members.map(m => m.id))
    if (merged.data.reminders.some(r => r.memberId && !ids.has(r.memberId))) throw Error('纪念日关联的成员已被另一端删除。')
  }
  catch (error) {
    // 两端分别合法的修改也可能合成环或悬空引用；交由用户选择完整关系图。
    return { data: clone(local), conflicts: [...merged.conflicts, `relationships:${error.message}`] }
  }
  return merged
}
function persist(ctx) { writeStorage(cacheKey(ctx.accountId, ctx.familyId), { version: 4, ...ctx.record }) }
function loadRecord(session, familyId) {
  const saved = readStorage(cacheKey(session.accountId, familyId))
  if (saved?.version === 4 && saved.working && saved.base) return saved
  const old = readStorage(`jiapu-data-v3:${session.accountId}`)
  const legacy = readStorage(`family-members-v2:${session.accountId}`, [])
  const working = old || { ...emptyData(), members: Array.isArray(legacy) ? legacy.filter(m => m?.name).map(m => ({ ...m, id: m.id || uid(), generation: generationFor(m.relation), parentIds: m.parentIds || [], spouseId: m.spouseId || '' })) : [] }
  if (!Array.isArray(working.members) || !Array.isArray(working.reminders) || !working.profile) throw Error('本机家谱格式异常，请先导出原始资料。')
  // 旧缓存只属于原账号的个人家族，不复制到共享家族。
  const migrate = !familyId || Number(familyId) === Number(readStorage(`family-owned-v4:${session.accountId}`))
  const data = migrate ? working : emptyData()
  return { base: emptyData(), working: clone(data), revision: 0, pending: !sameFamily(data, emptyData()), sequence: 0 }
}
export function remoteToLocal(payload) {
  const members = payload.members || [], idMap = new Map(members.map(m => [String(m.id), String(m.client_id || m.id)]))
  const data = {
    profile: { name: payload.profile?.name || '我的家谱', avatar: payload.profile?.avatar || '' },
    members: members.map(m => ({ id: String(m.client_id || m.id), name: m.name, relation: m.relation, gender: m.gender, generation: m.generation, birthday: m.birthday || '', deathYear: m.death_year || '', deathDate: m.death_date || '', deceased: !!m.deceased, avatarLabel: m.avatar_label || '', avatarName: m.avatar_name || '', bio: m.bio || '', parentIds: (m.parent_ids || []).map(id => idMap.get(String(id)) || String(id)), parentRoles: m.parent_roles || [], spouseId: m.spouse_id ? idMap.get(String(m.spouse_id)) || String(m.spouse_id) : '' })),
    reminders: (payload.reminders || []).map(r => ({ id: String(r.client_id || r.id), title: r.title, type: r.type, memberId: r.member_id ? idMap.get(String(r.member_id)) || String(r.member_id) : '', date: r.date, advance: r.advance, repeat: r.repeat, calendar_type: r.calendar_type || 'solar', lunar_month: r.lunar_month ?? null, lunar_day: r.lunar_day ?? null, is_leap: !!r.is_leap }))
  }
  return data
}
export function localToRemote(data, familyId = store.familyId, revision = store.revision) {
  return {
    family_id: familyId, revision, profile: data.profile,
    members: data.members.map(m => ({ client_id: String(m.id), name: m.name, relation: m.relation, gender: m.gender || '未知', generation: Number(m.generation) || generationFor(m.relation), birthday: m.birthday || null, death_year: m.deathYear ? String(m.deathYear) : null, death_date: m.deathDate || null, deceased: !!m.deceased, avatar_label: m.avatarLabel || '', avatar_name: m.avatarName || '', bio: m.bio || '', parent_ids: [], parent_client_ids: (m.parentIds || []).map(String), parent_roles: m.parentRoles || [], spouse_id: null, spouse_client_id: m.spouseId ? String(m.spouseId) : null })),
    reminders: data.reminders.map(r => ({ client_id: String(r.id), title: r.title, type: r.type, member_id: null, member_client_id: r.memberId || null, date: r.date, advance: typeof r.advance === 'number' ? r.advance ? `提前 ${r.advance} 天` : '当天' : r.advance || '当天', repeat: r.repeat || '每年', ...reminderCalendarFields(r) }))
  }
}
function apply(ctx) {
  if (!current(ctx)) return
  Object.assign(store, clone(ctx.record.working), { revision: ctx.record.revision })
}
function status(ctx, syncStatus, error = '') { if (current(ctx)) Object.assign(store, { syncStatus, error }) }
function acceptRemote(ctx, payload) {
  if (Number(payload.family_id) !== Number(ctx.familyId)) throw Error('收到其他家族的同步结果，已保留本机资料。')
  const remote = remoteToLocal(payload), local = ctx.record.working
  const merged = ctx.record.pending ? mergeChecked(ctx.record.base, local, remote) : { data: remote, conflicts: [] }
  const previousPending = !!ctx.record.pending
  ctx.record.role = payload.role || 'OWNER'
  if (previousPending && ctx.record.role === 'VIEWER') {
    ctx.permissionLost = true
    if (current(ctx)) Object.assign(store, { permissionLost: true, error: '当前家族权限已变为只读。本机未同步修改仍保留，请先导出或放弃后再切换家族。' })
  }
  if (ctx.record.role !== 'VIEWER') ctx.permissionLost = false
  ctx.record.permissionLost = !!ctx.permissionLost
  if (current(ctx)) store.role = ctx.record.role
  if (merged.conflicts.length) {
    ctx.record.working = merged.data
    apply(ctx)
    if (current(ctx)) Object.assign(store, { syncStatus: 'conflict', conflicts: merged.conflicts, syncConflict: { local: clone(local), remote, revision: payload.revision }, error: '本机与云端修改了相同资料，请选择保留内容。' })
    ctx.conflict = { ...merged, remote, revision: payload.revision }
    persist(ctx)
    return false
  }
  ctx.record.base = clone(remote); ctx.record.working = merged.data; ctx.record.revision = payload.revision
  ctx.record.pending = !sameFamily(merged.data, remote)
  if (current(ctx)) store.role = payload.role || 'OWNER'
  persist(ctx); apply(ctx)
  return true
}
export async function authenticatedRequest(path, options = {}) {
  const session = store.session
  const ctx = context
  if (!session?.accessToken || store.guest) throw Error('请先登录服务端账号。')
  if (ctx?.familyId && path.startsWith('/family/') && !/^\/family\/(list|active|personal|join-by-code|invitations\/incoming)(\?|$)/.test(path) && !/\/invitations\/\d+\/(accept|reject|cancel)$/.test(path)) {
    path += `${path.includes('?') ? '&' : '?'}family_id=${ctx.familyId}`
  }
  let result
  try { result = await request(path, { ...options, token: session.accessToken }) }
  catch (error) { if (error.status === 401) expireSession(ctx, error); throw error }
  if (!current(ctx) || store.session?.accessToken !== session.accessToken) throw Error('账号或家族已切换，请重新操作。')
  return result
}
async function pull(ctx, automatic = false) {
  const payload = await request(`/family/sync?family_id=${ctx.familyId}`, { token: ctx.token })
  if (!current(ctx)) return false
  if (automatic && store.editing) { status(ctx, ctx.conflict ? 'conflict' : ctx.record.pending ? 'pending' : 'synced'); return false }
  return acceptRemote(ctx, payload)
}
async function upload(ctx) {
  if (ctx.pullFlight) await ctx.pullFlight
  if (!current(ctx)) return { synced: false }
  if (ctx.flight) return ctx.flight
  ctx.flight = (async () => {
    let conflictsRetried = 0
    while (current(ctx) && ctx.record.pending && !ctx.conflict) {
      status(ctx, 'saving')
      const sent = clone(ctx.record.working), sequence = ctx.record.sequence
      try {
        const payload = await request('/family/sync', { method: 'PUT', data: localToRemote(sent, ctx.familyId, ctx.record.revision), token: ctx.token })
        if (!current(ctx)) return { synced: false }
        const remote = remoteToLocal(payload)
        if (Number(payload.family_id) !== Number(ctx.familyId)) throw Error('同步家族不匹配，未覆盖本机。')
        // 本次请求期间的新编辑与本次已保存快照合并，不用旧响应覆盖新编辑。
        const merged = ctx.record.sequence === sequence ? { data: remote, conflicts: [] } : mergeChecked(sent, ctx.record.working, remote)
        ctx.record.base = clone(remote); ctx.record.revision = payload.revision
        ctx.record.working = merged.data; ctx.record.pending = !sameFamily(merged.data, remote)
        if (merged.conflicts.length) {
          ctx.conflict = { remote, revision: payload.revision, conflicts: merged.conflicts }
          Object.assign(store, { syncStatus: 'conflict', conflicts: merged.conflicts, syncConflict: { local: clone(ctx.record.working), remote, revision: payload.revision } })
        }
        persist(ctx); apply(ctx); conflictsRetried = 0
      } catch (error) {
        if (!current(ctx)) return { synced: false }
        if (error.status === 409 && conflictsRetried++ < 3) {
          const payload = error.details?.remote || await request(`/family/sync?family_id=${ctx.familyId}`, { token: ctx.token })
          if (!current(ctx)) return { synced: false }
          if (acceptRemote(ctx, payload)) continue
          return { synced: false }
        }
        if (error.status === 403 && ctx.record.pending) {
          ctx.permissionLost = true
          if (current(ctx)) Object.assign(store, { permissionLost: true, role: 'VIEWER', syncStatus: 'error', error: '当前家族权限已变为只读。本机未同步修改仍保留，请先导出或放弃后再切换家族。' })
        } else status(ctx, error.network ? 'pending' : 'error', error.message)
        if (error.status === 401) expireSession(ctx, error)
        persist(ctx)
        return { synced: false }
      }
    }
    if (!current(ctx)) return { synced: false }
    status(ctx, ctx.conflict ? 'conflict' : 'synced')
    return { synced: !ctx.record.pending && !ctx.conflict }
  })().finally(() => { ctx.flight = null })
  return ctx.flight
}
export async function refreshFamily({ automatic = false } = {}) {
  const ctx = context
  if (!ctx?.token || store.guest) return { synced: false }
  if (automatic && store.editing) return { synced: false }
  if (ctx.refreshFlight) return ctx.refreshFlight
  ctx.refreshFlight = (async () => {
  if (ctx.flight) await ctx.flight
  if (!current(ctx)) return { synced: false }
  try {
    status(ctx, 'loading')
    ctx.pullFlight = pull(ctx, automatic).finally(() => { ctx.pullFlight = null })
    if (!await ctx.pullFlight) return { synced: false }
    if (ctx.record.pending) return upload(ctx)
    status(ctx, 'synced'); return { synced: true }
  } catch (error) { status(ctx, error.network ? 'pending' : 'error', error.message); if (error.status === 401) expireSession(ctx, error); return { synced: false } }
  })().finally(() => { ctx.refreshFlight = null })
  return ctx.refreshFlight
}
export async function retrySync(options) { return refreshFamily(options) }
export async function resolveSyncConflict(choice) {
  const ctx = context
  if (!ctx?.conflict) return { synced: false }
  const conflict = ctx.conflict
  ctx.record.working = clone(choice === 'remote' ? conflict.remote : ctx.record.working)
  ctx.record.base = clone(conflict.remote); ctx.record.revision = conflict.revision
  ctx.record.pending = choice !== 'remote'; ctx.conflict = null
  Object.assign(store, { conflicts: [], syncConflict: null })
  persist(ctx); apply(ctx)
  return choice === 'remote' ? (status(ctx, 'synced'), { synced: true }) : upload(ctx)
}
function activateContext(session, familyId) {
  store.editing = false
  clearAvatarCache()
  const record = loadRecord(session, familyId)
  context = { accountId: session.accountId, familyId, token: session.accessToken, epoch: ++epoch, record, conflict: null, flight: null }
  Object.assign(store, clone(record.working), { session, guest: false, user: session.user || null, familyId, role: record.role || (session.accessToken ? 'VIEWER' : 'OWNER'), revision: record.revision, syncStatus: record.pending ? 'pending' : 'idle', error: '', sessionValidated: false, conflicts: [], syncConflict: null, notifications: [], permissionLost: !!record.permissionLost, importRecoveryAvailable: !!readStorage(`family-import-previous:${session.accountId}:${familyId}`) })
  persist(context)
}
export async function activateSession(session, remember = true) {
  session = { ...session, accountId: String(session.accountId), storage: remember ? 'local' : 'session' }
  const familyId = session.user?.active_family_id || readStorage(activeKey(session.accountId)) || null
  activateContext(session, familyId)
  const activation = epoch
  // #ifdef H5
  if (typeof sessionStorage !== 'undefined') { sessionStorage.removeItem('family-auth-session'); if (!remember) sessionStorage.setItem('family-auth-session', JSON.stringify(session)) }
  // #endif
  if (remember) writeStorage(SESSION_KEY, session); else uni.removeStorageSync(SESSION_KEY)
  if (!session.accessToken) { store.syncStatus = 'local'; return { synced: false } }
  try {
    const user = await request('/auth/me', { token: session.accessToken })
    if (epoch !== activation) return { synced: false }
    store.user = user; store.session.user = user; store.sessionValidated = true
    const families = await request('/family/list', { token: session.accessToken })
    if (epoch !== activation) return { synced: false }
    const active = Array.isArray(families) ? families.find(f => f.active) : null
    if (active) { user.active_family_id = active.id; store.session.user = user }
    const owned = Array.isArray(families) ? families.find(f => Number(f.owner_id) === Number(user.id)) : null
    if (user.active_family_id && Number(user.active_family_id) !== Number(store.familyId)) {
      activateContext(store.session, user.active_family_id)
      store.sessionValidated = true
    }
    const selected = Array.isArray(families) ? families.find(f => Number(f.id) === Number(store.familyId)) : null
    if (selected) { context.record.role = selected.role; store.role = selected.role; persist(context) }
    if (owned) {
      writeStorage('family-owned-v4:' + session.accountId, owned.id)
      // 只在原账号自有家族中迁移尚未处理的旧缓存；旧副本保留供恢复。
      if (Number(owned.id) === Number(store.familyId) && !readStorage('family-legacy-migrated-v4:' + session.accountId)) {
        const old = readStorage('jiapu-data-v3:' + session.accountId) || loadRecord(session, null).working
        if (old && Array.isArray(old.members) && Array.isArray(old.reminders)) {
          const merged = mergeFamily(emptyData(), context.record.working, old)
          context.record.working = merged.data
          context.record.pending = true
          persist(context); apply(context)
        }
        writeStorage('family-legacy-migrated-v4:' + session.accountId, true)
      }
    }
    // 用户还没有家族时，GET sync 创建个人家族；只在此阶段允许分配 familyId。
    if (!store.familyId) {
      const ctx = context, payload = await request('/family/sync', { token: session.accessToken })
      if (!current(ctx)) return { synced: false }
      ctx.familyId = payload.family_id; store.familyId = payload.family_id
      writeStorage(activeKey(session.accountId), payload.family_id)
      if (!acceptRemote(ctx, payload)) return { synced: false }
      return ctx.record.pending ? upload(ctx) : (status(ctx, 'synced'), { synced: true })
    }
    writeStorage(activeKey(session.accountId), store.familyId)
    return refreshFamily()
  } catch (error) {
    if (epoch !== activation) return { synced: false }
    store.error = error.message; store.syncStatus = error.network ? 'pending' : 'error'
    if (error.status === 401) { expireSession(context, error); throw error }
    return { synced: false }
  }
}
export async function restoreSession() {
  let session
  store.sessionRestoring = true
  try {
    session = readStorage(SESSION_KEY)
    let remember = true
    // #ifdef H5
    if (!session && typeof sessionStorage !== 'undefined') {
      session = JSON.parse(sessionStorage.getItem('family-auth-session') || 'null')
      remember = false
    }
    // #endif
    if (matchesSession(session)) return await activateSession(session, remember && session.storage !== 'session')
    if (session) clearSavedSession()
  } catch (error) {
    if (error.status === 401 && store.session?.accessToken === session?.accessToken) {
      expireSession(context, error)
    }
    store.error = error.message; store.syncStatus = 'error'
  } finally { store.sessionRestoring = false }
}
function clearSavedSession() {
  uni.removeStorageSync(SESSION_KEY)
  // #ifdef H5
  if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('family-auth-session')
  // #endif
}
function expireSession(ctx, error) {
  if (!ctx || !current(ctx)) return
  clearSavedSession()
  ++epoch; context = null; clearAvatarCache()
  Object.assign(store, emptyData(), { session: null, guest: false, user: null, familyId: null, role: 'OWNER', revision: 0, editing: false, sessionValidated: false, notifications: [], conflicts: [], syncConflict: null, permissionLost: false, importRecoveryAvailable: false, error: error.message, syncStatus: 'error' })
}
export function enterGuest() {
  clearAvatarCache()
  ++epoch; context = null
  Object.assign(store, emptyData(), { session: { accountId: 'guest', username: '访客', authVersion: 0, isGuest: true }, guest: true, user: null, familyId: null, role: 'OWNER', revision: 0, editing: false, syncStatus: 'idle', sessionValidated: false, notifications: [], conflicts: [], syncConflict: null, permissionLost: false, importRecoveryAvailable: false, error: '' })
}
export async function logout() {
  const session = store.session
  ++epoch; context = null
  clearAvatarCache()
  clearSavedSession()
  Object.assign(store, emptyData(), { session: null, guest: false, user: null, familyId: null, role: 'OWNER', revision: 0, editing: false, syncStatus: 'idle', sessionValidated: false, notifications: [], conflicts: [], syncConflict: null, permissionLost: false, importRecoveryAvailable: false, error: '' })
  if (session?.accessToken) {
    await unregisterWebPush(session).catch(() => {})
    await unregisterMobilePush(session).catch(() => {})
    await unregisterWechatPush(session).catch(() => {})
    try { await request('/auth/logout', { method: 'POST', token: session.accessToken }) }
    catch { store.error = '已退出本机；服务器暂不可用，原会话未能撤销。可在登录设备管理中撤销。' }
  }
}
export async function switchFamily(id) {
  const previous = context
  const session = store.session
  if (previous?.record.pending) throw Error(previous.permissionLost ? '当前家谱权限已变为只读，请先导出本机修改或放弃后再切换家族。' : '当前家谱还有未同步资料，请先完成同步或解决冲突后切换家族。')
  const result = await authenticatedRequest('/family/active', { method: 'PUT', data: { family_id: Number(id) } })
  if (!current(previous) || store.session?.accessToken !== session?.accessToken) return { synced: false }
  session.user = { ...store.user, active_family_id: Number(id) }
  activateContext(session, Number(id)); store.sessionValidated = true
  writeStorage(activeKey(session.accountId), Number(id))
  if (!acceptRemote(context, result)) return { synced: false }
  if (context.record.pending) return upload(context)
  status(context, 'synced'); return { synced: true }
}
export async function joinFamilyByCode(code) {
  const previous = context, session = store.session
  if (!previous?.token || store.guest) throw Error('请先登录后使用邀请码。')
  if (previous.record.pending || previous.flight || previous.conflict) throw Error(previous.permissionLost ? '当前家谱权限已变为只读，请先导出本机修改或放弃后再加入。' : '当前家谱还有未同步资料，请先完成同步或解决冲突后加入。')
  const result = await authenticatedRequest('/family/join-by-code', { method: 'POST', data: { code } })
  if (!current(previous) || store.session?.accessToken !== session.accessToken) throw Error('账号或家族已切换，请重新操作。')
  session.user = { ...store.user, active_family_id: Number(result.family_id) }
  store.user = session.user
  activateContext(session, Number(result.family_id)); store.sessionValidated = true
  writeStorage(activeKey(session.accountId), Number(result.family_id))
  if (!acceptRemote(context, result)) return { synced: false }
  if (context.record.pending) return upload(context)
  status(context, 'synced'); return { synced: true }
}
export async function selectPersonalFamily() {
  const previous = context, session = store.session
  if (!previous?.token || store.guest) throw Error('请先登录后进入自己的家谱。')
  if (previous.record.pending || previous.flight || previous.conflict) throw Error(previous.permissionLost ? '当前家谱权限已变为只读，请先导出本机修改或放弃后再切换。' : '当前家谱还有未同步资料，请先完成同步或解决冲突后切换。')
  const result = await authenticatedRequest('/family/personal', { method: 'POST' })
  if (!current(previous) || store.session?.accessToken !== session.accessToken) throw Error('账号或家族已切换，请重新操作。')
  session.user = { ...store.user, active_family_id: Number(result.family_id) }; store.user = session.user
  activateContext(session, Number(result.family_id)); store.sessionValidated = true
  writeStorage(activeKey(session.accountId), Number(result.family_id))
  if (!acceptRemote(context, result)) return { synced: false }
  if (context.record.pending) return upload(context)
  status(context, 'synced'); return { synced: true }
}
function requireWrite() {
  if (!context || !store.session || store.guest) throw Error('访客模式仅支持浏览，请先登录。')
  if (store.role === 'VIEWER') throw Error('你只有查看权限，不能修改家谱。')
}
async function commit(changes) {
  requireWrite()
  const ctx = context
  ctx.record.working = clone({ ...snapshot(), ...changes }); ctx.record.sequence++
  ctx.record.pending = true; persist(ctx); apply(ctx)
  if (!ctx.token) { status(ctx, 'local', '这是旧本机账号，资料未上传。请导出后导入服务端账号。'); return { synced: false } }
  if (ctx.conflict) { status(ctx, 'conflict', '请先处理同步冲突；本次修改已保留本机。'); return { synced: false } }
  return upload(ctx)
}
export async function saveMember(raw) {
  requireWrite()
  const deceased = !!raw.deceased
  const member = { id: raw.id || uid(), name: String(raw.name || '').trim(), relation: raw.relation, gender: raw.gender || '未知', generation: Number(raw.generation) || generationFor(raw.relation), birthday: raw.birthday || '', birthYear: raw.birthYear ?? (raw.birthday ? Number(String(raw.birthday).slice(0, 4)) : null), deathYear: deceased && raw.deathYear ? String(raw.deathYear) : '', deathDate: deceased ? (raw.deathDate || '') : '', deceased, avatarLabel: raw.avatarLabel || '', avatarName: raw.avatarName || '', bio: raw.bio || '', parentIds: [...(raw.parentIds || [])], parentRoles: raw.parentRoles || [], spouseId: raw.spouseId || '' }
  if (member.birthday && !parseDate(member.birthday)) throw Error('出生日期无效。')
  if (!Number.isInteger(member.generation) || member.generation < 1 || member.generation > 100) throw Error('世代须为 1 至 100。')
  if (member.deathDate && (!parseDate(member.deathDate) || member.deathDate > dateString() || (member.birthday && member.deathDate < member.birthday))) throw Error('忌日应为出生日期与今天之间的有效日期。')
  if (member.deathDate) member.deathYear = member.deathDate.slice(0, 4)
  validateMember(member, store.members, dateString())
  const members = store.members.filter(m => m.id !== member.id).map(m => ({ ...m, spouseId: m.spouseId === member.id && m.id !== member.spouseId ? '' : m.spouseId }))
  const spouse = members.find(m => m.id === member.spouseId); if (spouse) spouse.spouseId = member.id
  const oldIndex = store.members.findIndex(m => m.id === member.id)
  members.splice(oldIndex < 0 ? members.length : oldIndex, 0, member)
  let reminders = store.reminders.map(r => r.memberId === member.id ? { ...r, member: member.name } : r)
  for (const [flag, type, date, label] of [['autoBirthday', 'birthday', member.birthday, '生日'], ['autoMemorial', 'memorial', member.deathDate, '忌日']]) {
    if (raw[flag] === undefined) continue
    const id = `auto-${type}-${member.id}`
    const previousReminder = reminders.find(r => r.id === id)
    reminders = reminders.filter(r => r.id !== id)
    if (raw[flag] && date) {
      const previousMember = store.members.find(m => m.id === member.id)
      const previousDate = type === 'birthday' ? previousMember?.birthday : previousMember?.deathDate
      const nextDate = previousReminder && previousDate === date ? previousReminder.date : date
      const reminder = { id, title: member.name + label, type, memberId: member.id, date: nextDate, advance: '当天', repeat: '每年', calendar_type: 'solar', ...previousReminder }
      reminder.date = nextDate; reminder.memberId = member.id
      if (!previousReminder || previousReminder.title === previousMember?.name + label) reminder.title = member.name + label
      if (previousReminder && nextDate !== previousReminder.date) Object.assign(reminder, reminderCalendarFields({ ...reminder, lunar_month: null, lunar_day: null, is_leap: undefined }))
      reminders.push(reminder)
    }
  }
  const result = await commit({ members, reminders })
  return { ...result, member }
}
export const saveParityMember = saveMember
export async function deleteMember(id) {
  const members = store.members.filter(m => m.id !== id).map(m => {
    const links = parentLinks(m, store.members).filter(link => link.id !== id)
    return { ...m, parentIds: links.map(link => link.id), parentRoles: links.map(link => link.role), spouseId: m.spouseId === id ? '' : m.spouseId }
  })
  const reminders = store.reminders.filter(r => !r.id.startsWith(`auto-`) || r.memberId !== id).map(r => r.memberId === id ? { ...r, memberId: '' } : r)
  return commit({ members, reminders })
}
export async function saveReminder(raw) {
  if (!raw.title?.trim()) throw Error('请填写提醒名称。')
  if (!parseDate(raw.date)) throw Error('请选择有效日期。')
  if (raw.memberId && !store.members.some(m => m.id === raw.memberId)) throw Error('关联成员已不存在。')
  const reminder = { id: raw.id || uid(), title: raw.title.trim(), type: raw.type, date: raw.date, advance: typeof raw.advance === 'number' ? raw.advance ? `提前 ${raw.advance} 天` : '当天' : raw.advance || '当天', repeat: raw.repeat || '每年', memberId: raw.memberId || '', ...reminderCalendarFields(raw) }
  return commit({ reminders: [...store.reminders.filter(r => r.id !== reminder.id), reminder] })
}
export const deleteReminder = id => commit({ reminders: store.reminders.filter(r => r.id !== id) })
export function saveProfile(profile) {
  if (!profile.name?.trim()) throw Error('请填写家族名称。')
  return commit({ profile: { name: profile.name.trim(), avatar: profile.avatar || '' } })
}
export const clearCurrentData = () => commit(emptyData())
export async function exportFamilyData() {
  const ctx = context, data = snapshot()
  if (data.profile.avatar) {
    const path = await resolveAvatar(data.profile.avatar)
    if (!path) throw Error('头像未加载完成，请重试导出。')
    const image = await readAvatarPayload(path)
    data.profile.avatar = `data:${image.content_type};base64,${image.data_base64}`
  }
  if (ctx && !current(ctx)) throw Error('账号或家族已切换，请重新导出。')
  return { format: 'jiapu-v4', exported_at: new Date().toISOString(), ...localToRemote(data), pending: !!ctx?.record.pending }
}
export async function importFamilyData(payload) {
  requireWrite()
  if (!payload || !Array.isArray(payload.members) || !Array.isArray(payload.reminders) || !payload.profile || payload.members.length > 10000 || payload.reminders.length > 10000) throw Error('文件不是有效的家谱备份。')
  const working = remoteToLocal({ ...payload, members: payload.members.map((m, i) => ({ ...m, id: m.id || i + 1 })), reminders: payload.reminders.map((r, i) => ({ ...r, id: r.id || i + 1 })) })
  const byClient = new Set(working.members.map(m => m.id))
  if (byClient.size !== working.members.length || new Set(working.reminders.map(r => r.id)).size !== working.reminders.length) throw Error('备份包含重复编号，请检查文件。')
  if (!working.profile.name?.trim() || working.profile.name.length > 64) throw Error('备份家族名称须为 1 至 64 个字。')
  working.members.forEach((m, i) => { m.parentIds = payload.members[i].parent_client_ids?.length ? payload.members[i].parent_client_ids.map(String) : m.parentIds; m.spouseId = String(payload.members[i].spouse_client_id || m.spouseId || '') })
  working.members.forEach(m => { if (!m.id || m.id.length > 64) throw Error('备份成员编号无效。'); validateMember(m, working.members, dateString()) })
  working.reminders.forEach((r, i) => {
    if (!r.id || r.id.length > 64) throw Error('备份提醒编号无效。')
    r.memberId = String(payload.reminders[i].member_client_id || r.memberId || '')
    if (r.memberId && !byClient.has(r.memberId)) throw Error('备份提醒引用了不存在的成员。')
    if (!r.title?.trim() || r.title.length > 128 || !parseDate(r.date) || !r.type?.trim() || r.type.length > 32 || !['每年', '仅一次'].includes(r.repeat)) throw Error('备份包含无效纪念日。')
    if (!/^(当天|提前\s*(1|3|7|15)\s*天)$/.test(r.advance)) throw Error('备份提醒提前时间不正确。')
    Object.assign(r, reminderCalendarFields(r))
  })
  const ctx = context
  // 服务端 save_snapshot 在同一事务内执行完整校验后才写入；本机先保留恢复副本，
  // 失败时可从导入导出页恢复，不会造成云端半写入。
  if (working.profile.avatar?.startsWith('data:')) working.profile.avatar = await persistAvatar(working.profile.avatar)
  if (!current(ctx)) throw Error('账号或家族已切换，请重新导入。')
  // 先写恢复副本，即便服务端拒绝，也不会丢失原始本机资料。
  writeStorage(`family-import-previous:${store.session.accountId}:${store.familyId}`, snapshot())
  ctx.record.importRecovery = true
  if (current(ctx)) store.importRecoveryAvailable = true
  return commit(working)
}

export function discardPendingChanges() {
  const ctx = context
  if (!ctx || !ctx.record.pending) return false
  ctx.record.working = clone(ctx.record.base)
  ctx.record.pending = false
  ctx.record.conflict = null
  ctx.conflict = null
  ctx.permissionLost = false
  persist(ctx); apply(ctx)
  if (current(ctx)) Object.assign(store, { permissionLost: false, conflicts: [], syncConflict: null, error: '', syncStatus: 'synced' })
  return true
}

export async function restorePreviousImport() {
  const ctx = context
  if (!ctx) throw Error('当前家族已切换，请重新打开恢复入口。')
  const previous = readStorage(`family-import-previous:${ctx.accountId}:${ctx.familyId}`)
  if (!previous) throw Error('没有可恢复的导入前资料。')
  const result = await commit(previous)
  if (result?.synced !== false) {
    ctx.record.importRecovery = false
    if (current(ctx)) store.importRecoveryAvailable = false
  }
  return result
}
export async function importLegacyLocalAccount(username, password) {
  requireWrite()
  if (!store.session?.accessToken) throw Error('请先登录服务端账号，再迁移旧本机资料。')
  const ctx = context
  const legacy = await verifyLegacyLocalAccount(username, password)
  if (!current(ctx)) throw Error('账号或家族已切换，请重新迁移。')
  const source = clone(loadRecord(legacy, null).working)
  if (!source.members.length && !source.reminders.length && sameFamily(source, emptyData())) throw Error('旧本机账号没有可迁移的家谱资料。')
  if (source.profile.avatar && !source.profile.avatar.startsWith('data:')) {
    const image = await readAvatarPayload(source.profile.avatar)
    source.profile.avatar = `data:${image.content_type};base64,${image.data_base64}`
  }
  if (!current(ctx)) throw Error('账号或家族已切换，请重新迁移。')
  // 旧账号和旧缓存原样保留；导入会先保存当前云账号的恢复副本。
  return importFamilyData(localToRemote(source, ctx.familyId, ctx.record.revision))
}
export function startSyncWatcher() {
  if (timer) return
  timer = setInterval(() => { if (context?.token && !store.guest && !context.flight && !context.conflict) refreshFamily({ automatic: true }) }, 30000)
  if (typeof uni.onNetworkStatusChange === 'function') uni.onNetworkStatusChange(r => { if (r.isConnected) retrySync({ automatic: true }) })
}
export function stopSyncWatcher() { clearInterval(timer); timer = null }
