import test from 'node:test'
import assert from 'node:assert/strict'
import { parentFields, formParentLinks, parentLinks, validateMember } from '../utils/family.js'
import { mergeFamily } from '../utils/sync.js'
import { store, activateSession, saveMember, deleteMember, refreshFamily, remoteToLocal, localToRemote, exportFamilyData, importFamilyData } from '../utils/store.js'

const profile = () => ({ name: '测试家族', avatar: '' })
const person = (id, extra = {}) => ({ id, name: id, relation: '其他亲属', generation: 3, gender: '未知', parentIds: [], parentRoles: [], spouseId: '', ...extra })
const parents = () => [person('father', { generation: 2 }), person('mother', { generation: 2 })]
const session = () => ({ authVersion: 2, accountId: 'relations-test', username: '关联测试', accessToken: 'mock-relations-token', user: { id: 1, active_family_id: 1 } })

// 只在内存模拟同步接口，同时分配数据库编号，避免用 client_id 回显掩盖映射错误。
function mockCloud(initialMembers = []) {
  const memory = new Map(), calls = [], ids = new Map()
  let nextId = 101, revision = 0, online = true
  const allocate = id => { if (!ids.has(id)) ids.set(id, nextId++); return ids.get(id) }
  function canonical(payload) {
    payload.members.forEach(m => allocate(m.client_id))
    return {
      family_id: 1, revision, role: 'OWNER', profile: payload.profile, reminders: [],
      members: payload.members.map(m => ({
        ...structuredClone(m), id: allocate(m.client_id),
        parent_ids: (m.parent_client_ids || []).map(id => ids.get(id)),
        spouse_id: m.spouse_client_id ? ids.get(m.spouse_client_id) : null
      }))
    }
  }
  let cloud = canonical({ profile: profile(), members: initialMembers.map(m => ({
    client_id: m.id, name: m.name, relation: m.relation, generation: m.generation, gender: m.gender,
    parent_client_ids: m.parentIds, parent_roles: m.parentRoles, spouse_client_id: m.spouseId || null
  })) })
  globalThis.uni = {
    getStorageSync: key => memory.get(key) ?? '',
    setStorageSync: (key, value) => memory.set(key, structuredClone(value)),
    removeStorageSync: key => memory.delete(key),
    request: options => {
      calls.push(options)
      if (options.url.endsWith('/auth/me')) return options.success({ statusCode: 200, data: { id: 1, active_family_id: 1 } })
      if (options.url.endsWith('/family/list')) return options.success({ statusCode: 200, data: [] })
      assert.match(options.url, /\/family\/sync(?:\?|$)/)
      if (!online) return options.fail({ errMsg: '模拟离线' })
      if (options.method === 'PUT') { revision++; cloud = canonical(options.data) }
      options.success({ statusCode: 200, data: structuredClone(cloud) })
    }
  }
  return { memory, calls, setOnline: value => { online = value }, cloud: () => structuredClone(cloud) }
}

test('仅选择母亲且性别未知时，编辑仍回填母亲栏', () => {
  const linked = { ...person('child'), ...formParentLinks({ parentOne: '', parentTwo: 'mother' }) }
  assert.deepEqual(linked.parentIds, ['mother'])
  assert.deepEqual(linked.parentRoles, ['mother'])
  assert.deepEqual(parentLinks(linked, parents()), [{ id: 'mother', role: 'mother' }])
  assert.deepEqual(parentFields(linked, parents()), { parentOne: '', parentTwo: 'mother' })
})

test('仅父亲和父母同时关联按明确角色回填，不受成员性别影响', () => {
  const members = [person('father', { gender: '女' }), person('mother', { gender: '男' })]
  assert.deepEqual(parentFields({ ...person('child'), ...formParentLinks({ parentOne: 'father', parentTwo: '' }) }, members), { parentOne: 'father', parentTwo: '' })
  assert.deepEqual(parentFields({ ...person('child'), ...formParentLinks({ parentOne: 'father', parentTwo: 'mother' }) }, members), { parentOne: 'father', parentTwo: 'mother' })
  assert.deepEqual(formParentLinks({ parentOne: '', parentTwo: '' }), { parentIds: [], parentRoles: [] })
})

test('旧家谱空角色兼容：已知母亲可识别，未知父母保留原顺序', () => {
  const mother = person('mother', { gender: '女' })
  assert.deepEqual(parentFields(person('child', { parentIds: ['mother'] }), [mother]), { parentOne: '', parentTwo: 'mother' })
  assert.deepEqual(parentFields(person('child', { parentIds: ['father', 'mother'] }), parents()), { parentOne: 'father', parentTwo: 'mother' })
  assert.equal(validateMember(person('child', { parentIds: ['mother'] }), [mother], '2026-10-12'), true)
})

test('母亲角色随同步、数据库编号转换和重新登录保留', async () => {
  const mock = mockCloud(parents())
  await activateSession(session())
  const result = await saveMember({ ...person('child'), ...formParentLinks({ parentOne: '', parentTwo: 'mother' }) })
  assert.equal(result.synced, true)
  const sent = mock.calls.findLast(o => o.method === 'PUT').data.members.find(m => m.client_id === 'child')
  assert.deepEqual(sent.parent_client_ids, ['mother'])
  assert.deepEqual(sent.parent_roles, ['mother'])
  const cloudChild = mock.cloud().members.find(m => m.client_id === 'child')
  assert.ok(cloudChild.parent_ids.every(id => typeof id === 'number'))
  await refreshFamily()
  await activateSession(session())
  assert.equal(store.syncStatus, 'synced')
  assert.deepEqual(parentFields(store.members.find(m => m.id === 'child'), store.members), { parentOne: '', parentTwo: 'mother' })
})

test('删除父亲后父母编号和角色同步删除，母亲不会移到父亲栏', async () => {
  const mock = mockCloud([...parents(), { ...person('child'), ...formParentLinks({ parentOne: 'father', parentTwo: 'mother' }) }])
  await activateSession(session())
  await deleteMember('father')
  const child = store.members.find(m => m.id === 'child')
  assert.deepEqual(child.parentIds, ['mother'])
  assert.deepEqual(child.parentRoles, ['mother'])
  assert.deepEqual(parentFields(child, store.members), { parentOne: '', parentTwo: 'mother' })
  const cloudChild = mock.cloud().members.find(m => m.client_id === 'child')
  assert.deepEqual(cloudChild.parent_roles, ['mother'])
  await refreshFamily()
  assert.deepEqual(parentFields(store.members.find(m => m.id === 'child'), store.members), { parentOne: '', parentTwo: 'mother' })
})

test('离线保存母亲关联，恢复联网后补传角色', async () => {
  const mock = mockCloud(parents())
  await activateSession(session())
  mock.setOnline(false)
  assert.equal((await saveMember({ ...person('child'), ...formParentLinks({ parentOne: '', parentTwo: 'mother' }) })).synced, false)
  assert.equal(store.syncStatus, 'pending')
  mock.setOnline(true)
  await refreshFamily()
  assert.equal(store.syncStatus, 'synced')
  assert.deepEqual(mock.cloud().members.find(m => m.client_id === 'child').parent_roles, ['mother'])
  assert.deepEqual(parentFields(store.members.find(m => m.id === 'child'), store.members), { parentOne: '', parentTwo: 'mother' })
})

test('导出导入保留母亲角色和配偶双向关联', async () => {
  mockCloud([...parents(), { ...person('child'), ...formParentLinks({ parentOne: '', parentTwo: 'mother' }), spouseId: 'partner' }, person('partner', { spouseId: 'child' })])
  await activateSession(session())
  const backup = await exportFamilyData()
  assert.deepEqual(backup.members.find(m => m.client_id === 'child').parent_roles, ['mother'])
  await importFamilyData(backup)
  const child = store.members.find(m => m.id === 'child'), partner = store.members.find(m => m.id === 'partner')
  assert.deepEqual(parentFields(child, store.members), { parentOne: '', parentTwo: 'mother' })
  assert.equal(child.spouseId, 'partner')
  assert.equal(partner.spouseId, 'child')
})

test('更换和解除配偶会更新双方，释放旧配偶', async () => {
  mockCloud([person('a'), person('b'), person('c')])
  await activateSession(session())
  await saveMember({ ...store.members.find(m => m.id === 'a'), spouseId: 'b' })
  assert.equal(store.members.find(m => m.id === 'b').spouseId, 'a')
  await saveMember({ ...store.members.find(m => m.id === 'a'), spouseId: 'c' })
  assert.equal(store.members.find(m => m.id === 'b').spouseId, '')
  assert.equal(store.members.find(m => m.id === 'c').spouseId, 'a')
  await saveMember({ ...store.members.find(m => m.id === 'a'), spouseId: '' })
  assert.equal(store.members.find(m => m.id === 'c').spouseId, '')
})

test('非法父母角色、重复角色和长度不匹配均在保存前拒绝', async () => {
  const mock = mockCloud(parents())
  await activateSession(session())
  const before = structuredClone(JSON.parse(JSON.stringify(store.members)))
  for (const extra of [
    { parentIds: ['mother'], parentRoles: ['spouse'] },
    { parentIds: ['father', 'mother'], parentRoles: ['mother', 'mother'] },
    { parentIds: ['mother'], parentRoles: ['father', 'mother'] }
  ]) {
    await assert.rejects(saveMember({ ...person('child'), ...extra }), /角色|父母|父亲|母亲/)
    assert.deepEqual(JSON.parse(JSON.stringify(store.members)), before)
  }
  assert.equal(mock.calls.filter(o => o.method === 'PUT').length, 0)
  assert.equal(validateMember(person('child', { parentIds: ['mother'], parentRoles: ['parent'] }), parents(), '2026-10-12'), true)
})

test('非法备份角色不会替换本机成员资料', async () => {
  mockCloud(parents())
  await activateSession(session())
  const backup = await exportFamilyData(), before = JSON.parse(JSON.stringify(store.members))
  backup.members.push({ client_id: 'child', name: 'child', relation: '其他亲属', generation: 3, gender: '未知', parent_client_ids: ['mother'], parent_roles: ['spouse'] })
  await assert.rejects(importFamilyData(backup), /角色|父母|父亲|母亲/)
  assert.deepEqual(JSON.parse(JSON.stringify(store.members)), before)
})

test('API 与本机转换保留角色，旧服务端没有角色字段仍兼容', () => {
  const source = { profile: profile(), members: [...parents(), { ...person('child'), ...formParentLinks({ parentOne: '', parentTwo: 'mother' }) }], reminders: [] }
  const remote = localToRemote(source, 1, 0)
  assert.deepEqual(remote.members.find(m => m.client_id === 'child').parent_roles, ['mother'])
  const legacy = remoteToLocal({ profile: profile(), members: [{ id: 1, client_id: 'mother', name: '母亲', relation: '母亲', gender: '女', parent_ids: [] }, { id: 2, client_id: 'child', name: '孩子', relation: '本人', parent_ids: [1] }], reminders: [] })
  assert.deepEqual(parentFields(legacy.members[1], legacy.members), { parentOne: '', parentTwo: 'mother' })
})

test('两端分别改父母编号和角色时产生冲突，编号与角色保持来自同一端', () => {
  const base = { profile: profile(), members: [...parents(), person('child', { parentIds: ['father'] })], reminders: [] }
  const local = structuredClone(base), remote = structuredClone(base)
  local.members[2].parentRoles = ['mother']
  remote.members[2].parentIds = ['mother']
  remote.members[2].name = '云端改名'
  const merged = mergeFamily(base, local, remote)
  assert.ok(merged.conflicts.includes('members:child.parentIds'))
  assert.deepEqual(merged.data.members[2].parentIds, ['father'])
  assert.deepEqual(merged.data.members[2].parentRoles, ['mother'])
  assert.equal(merged.data.members[2].name, '云端改名')
})
