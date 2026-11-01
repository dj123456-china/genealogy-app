import test from 'node:test'
import assert from 'node:assert/strict'
import { pbkdf2Sync } from 'node:crypto'
import { generationFor, genderFor, analyzeRelationship, validateMember, inferYears, DEMO_MEMBERS } from '../utils/family.js'
import { nextOccurrence, remindersForDate, dayDistance, lunarDate, qingmingDate, parseDate } from '../utils/dates.js'
import { signInOrRegister, signInWithPhone, matchesSession } from '../utils/auth.js'
const storage = new Map()
globalThis.uni = { getStorageSync: k => storage.get(k) ?? '', setStorageSync: (k, v) => storage.set(k, v) }
test('关系沿真实父母方向计算：父子、祖孙、兄妹，不能混淆', () => {
  assert.equal(analyzeRelationship(DEMO_MEMBERS, 'd3', 'd6').title, '亲子关系')
  assert.equal(analyzeRelationship(DEMO_MEMBERS, 'd1', 'd6').title, '祖孙关系')
  assert.equal(analyzeRelationship(DEMO_MEMBERS, 'd6', 'd7').title, '兄弟姐妹关系')
  assert.equal(analyzeRelationship(DEMO_MEMBERS, 'd1', 'd2').title, '夫妻关系')
  assert.equal(analyzeRelationship(DEMO_MEMBERS, 'd1', 'd1').ok, false)
  assert.equal(analyzeRelationship(DEMO_MEMBERS, 'missing', 'd2').ok, false)
})
test('祖孙称谓不降级成亲子，子女是本人下一代', () => {
  assert.equal(generationFor('子女'), 4)
  assert.equal(generationFor('祖母'), 1)
  const list = [{ id: 'a', name: '本人甲', relation: '本人' }, { id: 'b', name: '祖父乙', relation: '祖父' }]
  assert.match(analyzeRelationship(list, 'a', 'b').message, /祖父/)
  assert.equal(inferYears('2030', '1990', 2026).ok, false)
})
test('明确称谓同步性别，关联父母后世代按真实父母计算', () => {
  assert.equal(genderFor('父亲'), '男')
  assert.equal(genderFor('母亲'), '女')
  assert.equal(genderFor('兄弟'), '未知')
  const members = [{ id: 'p', generation: 6 }, { id: 'm', generation: 7 }]
  assert.equal(generationFor('子女', members, ['p', 'm']), 8)
  assert.equal(generationFor('子女'), 4)
})
test('父母与子女的出生年份顺序必须合理', () => {
  const parent = { id: 'p', name: '父母', birthday: '1980-01-01', parentIds: [] }
  const child = { id: 'c', name: '子女', relation: '子女', birthday: '2010-01-01', parentIds: ['p'] }
  assert.equal(validateMember(child, [parent], '2026-10-18'), true)
  assert.throws(() => validateMember({ ...child, birthday: '1970-01-01' }, [parent], '2026-10-18'), /出生日期不能早于或等于父母/)
  assert.throws(() => validateMember({ ...child, birthYear: 2009 }, [parent], '2026-10-18'), /出生年份与出生日期不一致/)
})
test('卒年必须有效且不能早于出生年或晚于今年', () => {
  const base = { id: 'p', name: '成员', relation: '其他亲属', birthday: '1950-01-01', parentIds: [] }
  assert.equal(validateMember({ ...base, deathYear: '2020' }, [], '2026-10-18'), true)
  assert.throws(() => validateMember({ ...base, deathYear: '1949' }, [], '2026-10-18'), /卒年应在出生年份与当前年份之间/)
  assert.throws(() => validateMember({ ...base, deathYear: '2027' }, [], '2026-10-18'), /卒年应在出生年份与当前年份之间/)
  assert.throws(() => validateMember({ ...base, deathYear: '20' }, [], '2026-10-18'), /卒年应在出生年份与当前年份之间/)
})
test('成员校验允许同名，拒绝重复本人和循环世系', () => {
  const base = { id: 'a', name: '甲', relation: '本人', parentIds: [] }
  assert.equal(validateMember({ ...base, id: 'b', relation: '父亲' }, [base], '2026-09-20'), true)
  assert.throws(() => validateMember({ ...base, id: 'b', name: '乙' }, [base], '2026-09-20'), /本人/)
  assert.throws(() => validateMember({ ...base, parentIds: ['b'] }, [base, { id: 'b', name: '乙', relation: '子女', parentIds: ['a'] }], '2026-09-20'), /循环/)
  assert.throws(() => validateMember({ ...base, deathYear: '1800', birthday: '1950-01-01' }, [], '2026-09-20'), /卒年/)
})
test('年度提醒跨年，闰日不会错误地滑到三月', () => {
  assert.equal(nextOccurrence({ date: '2000-02-29', repeat: '每年' }, new Date(2026, 8, 20)), '2028-02-29')
  assert.equal(nextOccurrence({ date: '2000-09-19', repeat: '每年' }, new Date(2026, 8, 20)), '2027-09-19')
  assert.equal(nextOccurrence({ date: '2000-09-20', repeat: '每年' }, new Date(2026, 8, 20)), '2026-09-20')
  assert.equal(nextOccurrence({ date: '2026-09-19', repeat: '仅一次' }, new Date(2026, 8, 20)), '2026-09-19')
  assert.equal(remindersForDate([{ date: '2026-09-20', repeat: '每年' }], '2025-09-20').length, 0)
  assert.equal(dayDistance('2026-09-21', new Date(2026, 8, 20, 23, 59)), 1)
  assert.equal(parseDate('2026-02-29'), null)
})
test('农历和清明按真实日历换算', () => {
  assert.equal(lunarDate('2026-02-17'), '农历正月初一')
  assert.equal(qingmingDate(2026), '2026-04-05')
  assert.equal(qingmingDate(2024), '2024-04-04')
})
test('跨平台登录兼容旧 PBKDF2，错误密码不创建或覆盖账号', async () => {
  storage.clear()
  const salt = '00112233445566778899aabbccddeeff'
  const passwordHash = pbkdf2Sync('password1', Buffer.from(salt, 'hex'), 600000, 32, 'sha256').toString('hex')
  storage.set('family-local-accounts-v1', JSON.stringify([{ id: '0123456789abcdef0123456789abcdef', username: '旧账号', version: 1, salt, iterations: 600000, passwordHash }]))
  const old = await signInOrRegister('旧账号', 'password1')
  assert.equal(old.isNew, false)
  assert.equal(matchesSession(old), true)
  await assert.rejects(signInOrRegister('旧账号', 'wrong123'), /密码不正确/)
  const fresh = await signInOrRegister('NewUser', 'abcdef123')
  assert.equal(fresh.isNew, true)
  const again = await signInOrRegister('newuser', 'abcdef123')
  assert.equal(again.accountId, fresh.accountId)
  assert.equal(again.isNew, false)
  assert.equal(storage.get('family-local-accounts-v1').length, 2)
  assert.ok(!JSON.stringify(storage.get('family-local-accounts-v1')).includes('abcdef123'))
})

test('无 TextEncoder 的 App 逻辑层也能校验 Unicode 密码', async () => {
  const { utf8Bytes } = await import('../utils/encoding.js')
  for (const value of ['abc', '家谱😀密码', '\ud800', '\udc00', 'é']) assert.deepEqual(Buffer.from(utf8Bytes(value)), Buffer.from(value))
  const encoder = globalThis.TextEncoder
  try {
    globalThis.TextEncoder = undefined
    storage.clear()
    const session = await signInOrRegister('移动端', '家谱😀密码123')
    const account = storage.get('family-local-accounts-v1')[0]
    assert.equal(account.passwordHash, pbkdf2Sync('家谱😀密码123', Buffer.from(account.salt, 'hex'), 600000, 32, 'sha256').toString('hex'))
    assert.equal(matchesSession(session), true)
  } finally { globalThis.TextEncoder = encoder }
})

test('手机号登录兼容原账号，拒绝无效号码和错误密码，隔离不同号码', async () => {
  storage.clear()
  for (const phone of ['', '123', '12812345678', '138001380000', '1380013800a']) {
    await assert.rejects(signInWithPhone(phone, 'password1'), /11 位手机号/)
  }
  assert.equal(storage.size, 0)
  const existing = await signInOrRegister('13800138000', 'password1')
  const login = await signInWithPhone(' １３８００１３８０００ ', 'password1')
  assert.equal(login.accountId, existing.accountId)
  assert.equal(login.isNew, false)
  assert.equal(matchesSession(login), true)
  const before = JSON.stringify(storage.get('family-local-accounts-v1'))
  await assert.rejects(signInWithPhone('13800138000', 'incorrect'), /密码不正确/)
  assert.equal(JSON.stringify(storage.get('family-local-accounts-v1')), before)
  const other = await signInWithPhone('13900139000', 'password2')
  assert.equal(other.isNew, true)
  assert.notEqual(other.accountId, existing.accountId)
  assert.equal((await signInWithPhone('13900139000', 'password2')).accountId, other.accountId)
})


test('空账号没有提醒和日历标记，已有提醒按真实日期展示', async () => {
  const { reminderViews, calendarDays } = await import('../utils/parity-domain.js')
  const today = new Date(2026, 8, 20)
  assert.deepEqual(reminderViews([], today), [])
  assert.ok(calendarDays(2026, 8, []).every(day => !day.type))
  const reminders = [
    {id:'annual',title:'自建生日',date:'2000-09-21',repeat:'每年',type:'birthday'},
    {id:'past',title:'已结束祭日',date:'2026-09-01',repeat:'仅一次',type:'festival'},
    {id:'future',title:'自建安排',date:'2026-10-01',repeat:'仅一次',type:'festival'}
  ]
  const rows = reminderViews(reminders, today)
  assert.deepEqual(rows.map(r => r.id), ['past','annual','future'])
  assert.equal(rows[1].occurrence, '2026-09-21')
  assert.equal(rows[1].countdown, '还有 1 天')
  assert.deepEqual(rows.filter(r => r.days >= 0).map(r => r.id), ['annual','future'])
  assert.equal(calendarDays(2026,8,reminders).find(day => day.date === '2026-09-21').type, 'birthday')
  assert.deepEqual(reminderViews([], today), [])
})
