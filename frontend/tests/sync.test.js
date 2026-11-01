import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeFamily } from '../utils/sync.js'
import { nextOccurrence, remindersForDate, reminderCalendarFields } from '../utils/dates.js'
import { store, activateSession, saveMember, saveReminder, refreshFamily, remoteToLocal, localToRemote, resolveSyncConflict, enterGuest, switchFamily, importFamilyData, authenticatedRequest, deleteMember, importLegacyLocalAccount } from '../utils/store.js'
import { pbkdf2Sync } from 'node:crypto'

const empty = () => ({ profile: { name: '江氏家族', avatar: '' }, members: [], reminders: [] })
const tick = () => new Promise(resolve => setImmediate(resolve))
const response = (data = empty(), familyId = 1, revision = 0) => ({ family_id: familyId, revision, role: 'OWNER', ...data })
function mock(handler) {
  const memory = new Map(), calls = []
  globalThis.uni = { getStorageSync: k => memory.get(k) ?? '', setStorageSync: (k,v) => memory.set(k, structuredClone(v)), removeStorageSync: k => memory.delete(k), request: options => { calls.push(options); handler(options) } }
  return { memory, calls }
}
const ok = (o, data) => o.success({ statusCode: 200, data })
function session(id='1',familyId=1) { return { authVersion: 2, accountId:id,username:'用户'+id,accessToken:'token-'+id,user:{id:Number(id),active_family_id:familyId} } }
const me = o => ok(o,{id:1,username:'用户1',active_family_id:1})
const canonical = (o, revision = 1) => response({ ...o.data, members:o.data.members.map((m,i)=>({...m,id:i+1})), reminders:o.data.reminders.map((r,i)=>({...r,id:i+1})) }, o.data.family_id, revision)

test('三方合并保留离线新增和服务器独立修改，冲突不静默覆盖', () => {
  const base = { ...empty(), members:[{id:'a',name:'甲',bio:'旧'}] }
  const local = { ...base, members:[{id:'a',name:'甲',bio:'本机'}, {id:'b',name:'乙'}] }
  const remote = { ...base, profile:{name:'新名称',avatar:''} }
  const result = mergeFamily(base,local,remote)
  assert.deepEqual(result.conflicts,[])
  assert.equal(result.data.members.length,2)
  assert.equal(result.data.profile.name,'新名称')
  const conflict = mergeFamily(base,local,{...remote,members:[{id:'a',name:'甲',bio:'云端'}]})
  assert.deepEqual(conflict.conflicts,['members:a.bio'])
  assert.equal(conflict.data.members[0].bio,'本机')
})
test('卒年发送字符串，回写保持client_id和关系，不丢稳定提醒ID', () => {
  const source = {...empty(),members:[{id:'m',name:'甲',relation:'本人',deathYear:2018}],reminders:[{id:'r',memberId:'m',title:'忌日',date:'2018-01-01',repeat:'每年',advance:'当天'}]}
  assert.equal(localToRemote(source,1,0).members[0].death_year,'2018')
  const normalized = remoteToLocal(response({...empty(),members:[{id:88,client_id:'m',name:'甲',death_year:'2018',parent_ids:[]}],reminders:[{id:99,client_id:'r',member_id:88,title:'忌日',date:'2018-01-01'}]}))
  assert.equal(normalized.reminders[0].id,'r')
  assert.equal(normalized.reminders[0].memberId,'m')
})
test('农历春节按农历年重复，清明日期逐年换算', () => {
  const r={date:'2026-02-17',repeat:'每年',calendar_type:'lunar',...reminderCalendarFields({date:'2026-02-17',calendar_type:'lunar'})}
  assert.equal(nextOccurrence(r,new Date(2026,9,10)),'2027-02-06')
  assert.equal(remindersForDate([r],'2027-02-06').length,1)
  assert.equal(nextOccurrence({date:'2024-04-04',repeat:'每年',calendar_type:'qingming'},new Date(2026,0,1)),'2026-04-05')
})
test('断网保存保留pending；联网拉取后合并补传而非删除离线成员', async () => {
  let online=true, revision=0, cloud=response()
  mock(o => {
    if(o.url.endsWith('/auth/me')) return me(o)
    if(!online) return o.fail()
    if(o.method==='PUT') { revision++; cloud=response({...o.data,members:o.data.members.map((m,i)=>({...m,id:i+1})),reminders:[]},1,revision) }
    ok(o,cloud)
  })
  await activateSession(session())
  online=false
  const saved=await saveMember({name:'离线成员',relation:'本人'})
  assert.equal(saved.synced,false)
  assert.equal(store.members.length,1)
  assert.equal(store.syncStatus,'pending')
  online=true
  await refreshFamily()
  assert.equal(store.members.length,1)
  assert.equal(cloud.members.length,1)
  assert.equal(store.syncStatus,'synced')
})
test('迟到的旧账号拉取不覆盖新账号', async () => {
  let delayed
  mock(o => {
    if(o.url.endsWith('/auth/me')) return ok(o,{id:o.header.Authorization.endsWith('1')?1:2,username:'测试',active_family_id:o.header.Authorization.endsWith('1')?1:2})
    if(o.header.Authorization.endsWith('1')) { delayed=o; return }
    ok(o,response({...empty(),profile:{name:'乙家族',avatar:''}},2))
  })
  const first=activateSession(session('1',1)); await tick()
  await activateSession(session('2',2))
  ok(delayed,response({...empty(),profile:{name:'甲家族',avatar:''}},1))
  await first
  assert.equal(store.session.accountId,'2'); assert.equal(store.profile.name,'乙家族')
})
test('连续保存串行提交，旧响应不覆盖新编辑', async () => {
  let held, puts=0
  mock(o => {
    if(o.url.endsWith('/auth/me'))return me(o)
    if(o.method==='PUT') {
      puts++
      if(puts===1){held=o;return}
      return ok(o,response({...o.data,members:o.data.members.map((m,i)=>({...m,id:i+1})),reminders:o.data.reminders.map((r,i)=>({...r,id:i+1}))},1,puts))
    }
    ok(o,response())
  })
  await activateSession(session())
  const first=saveMember({name:'甲',relation:'本人'})
  await tick()
  const second=saveMember({name:'乙',relation:'父亲'})
  assert.equal(puts,1)
  ok(held,response({...held.data,members:held.data.members.map((m,i)=>({...m,id:i+1})),reminders:[]},1,1))
  await Promise.all([first,second])
  assert.equal(puts,2); assert.equal(store.members.length,2); assert.equal(store.syncStatus,'synced')
})
test('成员和自动提醒单次提交，拒绝循环关系', async () => {
  let last
  mock(o => { if(o.url.endsWith('/auth/me'))return me(o); if(o.method==='PUT'){last=o;return ok(o,response({...o.data,members:o.data.members.map((m,i)=>({...m,id:i+1})),reminders:o.data.reminders.map((r,i)=>({...r,id:i+1,member_id:1}))},1,1))}ok(o,response()) })
  await activateSession(session())
  const result=await saveMember({name:'甲',relation:'本人',birthday:'1990-01-01',autoBirthday:true})
  assert.equal(last.data.members.length,1);assert.equal(last.data.reminders.length,1)
  assert.equal(last.data.reminders[0].member_client_id,result.member.id)
  await assert.rejects(saveMember({...result.member,parentIds:[result.member.id]}),/自己/)
})
test('切换家族的旧账号响应不改变新账号上下文', async () => {
  let delayed
  mock(o => {
    const id=o.header.Authorization.endsWith('1')?1:2
    if(o.url.endsWith('/auth/me'))return ok(o,{id,active_family_id:id})
    if(o.url.endsWith('/family/active')){delayed=o;return}
    ok(o,response({...empty(),profile:{name:'家族'+id,avatar:''}},id))
  })
  await activateSession(session())
  const switching=switchFamily(10);await tick()
  await activateSession(session('2',2))
  ok(delayed,response(empty(),10));await assert.rejects(switching,/已切换/)
  assert.equal(store.session.accountId,'2');assert.equal(store.familyId,2);assert.equal(store.profile.name,'家族2')
})
test('错误备份不会替换原本家谱，合法同名备份可以导入', async () => {
  mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(o.method==='PUT')return ok(o,canonical(o));ok(o,response())})
  await activateSession(session())
  await saveMember({name:'原资料',relation:'本人'})
  const before=JSON.parse(JSON.stringify(store.members))
  const person={client_id:'same',name:'同名',relation:'父亲',generation:2,gender:'男',parent_client_ids:[]}
  await assert.rejects(importFamilyData({...empty(),members:[person,person]}),/重复编号/)
  assert.deepEqual(store.members,before)
  await assert.rejects(importFamilyData({...empty(),members:[{...person,birthday:'2026-02-29'}]}),/日期/)
  assert.deepEqual(store.members,before)
  await importFamilyData({...empty(),members:[person,{...person,client_id:'other',relation:'叔父'}]})
  assert.equal(store.members.length,2);assert.equal(store.members[0].name,store.members[1].name)
})
test('选择本机冲突字段仍保留云端独立新增', async () => {
  const base=response({...empty(),members:[{id:1,client_id:'a',name:'甲',relation:'本人',gender:'男',generation:3,bio:'旧',parent_ids:[]}]})
  let cloud=base,offline=false,put
  mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(offline)return o.fail();if(o.method==='PUT'){put=o;cloud=canonical(o,2)}ok(o,cloud)})
  await activateSession(session());offline=true
  await saveMember({...store.members[0],bio:'本机'})
  offline=false;cloud=response({...empty(),members:[{...base.members[0],bio:'云端'},{id:2,client_id:'b',name:'乙',relation:'父亲',generation:2,parent_ids:[]}]},1,1)
  await refreshFamily();assert.equal(store.syncStatus,'conflict')
  await resolveSyncConflict('local')
  assert.equal(put.data.members.find(m=>m.client_id==='a').bio,'本机')
  assert.ok(put.data.members.some(m=>m.client_id==='b'))
})
test('刷新期间保存等待拉取合并，过期会话不再显示已验证', async () => {
  let held,hold=false,puts=0,expired=false
  mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(expired)return o.success({statusCode:401,data:{detail:'登录已过期'}});if(o.method==='PUT'){puts++;return ok(o,canonical(o))}if(hold&&o.url.includes('/sync')){held=o;return}ok(o,response())})
  await activateSession(session());hold=true
  const refreshing=refreshFamily();await tick()
  const saving=saveMember({name:'等待拉取',relation:'本人'});await tick()
  assert.equal(puts,0)
  hold=false;ok(held,response());await Promise.all([refreshing,saving])
  assert.equal(puts,1);assert.equal(store.members[0].name,'等待拉取')
  expired=true;await refreshFamily();assert.equal(store.sessionValidated,false);assert.equal(store.syncStatus,'error')
})
test('旧个人缓存不能迁移到共享家族；服务端active纠正旧本机选择', async () => {
  const {memory}=mock(o=>{if(o.url.endsWith('/auth/me'))return ok(o,{id:1,active_family_id:99});if(o.url.endsWith('/family/list'))return ok(o,[{id:2,owner_id:2,role:'VIEWER',active:true}]);ok(o,{...response(empty(),2),role:'VIEWER'})})
  memory.set('jiapu-data-v3:1',{...empty(),members:[{id:'private',name:'私有成员',relation:'本人'}]})
  await activateSession(session('1',99))
  assert.equal(store.familyId,2);assert.equal(store.members.length,0);assert.equal(store.role,'VIEWER')
  await assert.rejects(saveMember({name:'不允许',relation:'本人'}),/查看权限/)
})
test('账户工具迟到响应中止后续操作，避免影响新账号', async () => {
  let held
  mock(o=>{const id=o.header.Authorization.endsWith('1')?1:2;if(o.url.endsWith('/auth/me'))return ok(o,{id,active_family_id:id});if(o.url.endsWith('/auth/sessions')){held=o;return}ok(o,response(empty(),id))})
  await activateSession(session())
  const pending=authenticatedRequest('/auth/sessions')
  await activateSession(session('2',2));ok(held,[])
  await assert.rejects(pending,/已切换/);assert.equal(store.familyId,2)
})
test('合并悬空的提醒关联转为可处理冲突', async () => {
  const original={id:1,client_id:'a',name:'甲',relation:'本人',generation:3,parent_ids:[]}
  let cloud=response({...empty(),members:[original]}),offline=false
  mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(offline)return o.fail();ok(o,cloud)})
  await activateSession(session());offline=true;await deleteMember('a');offline=false
  cloud=response({...empty(),members:[original],reminders:[{id:2,client_id:'r',member_id:1,title:'云端新增',date:'2026-10-10',repeat:'每年',advance:'当天',type:'birthday'}]},1,1)
  await refreshFamily();assert.equal(store.syncStatus,'conflict');assert.ok(store.conflicts.some(c=>c.startsWith('relationships:')))
  await resolveSyncConflict('remote');assert.equal(store.members.length,1);assert.equal(store.reminders[0].memberId,'a')
})
test('旧本机账号验证后迁移到云账号，保留旧缓存和导入前副本', async () => {
  const {memory}=mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(o.method==='PUT')return ok(o,canonical(o));ok(o,response())})
  const id='0123456789abcdef0123456789abcdef',salt='00112233445566778899aabbccddeeff'
  const old={...empty(),members:[{id:'old-member',name:'旧资料',relation:'父亲',generation:2,parentIds:[],spouseId:''}]}
  memory.set('family-local-accounts-v1',[{id,username:'旧账号',version:1,salt,iterations:600000,passwordHash:pbkdf2Sync('password1',Buffer.from(salt,'hex'),600000,32,'sha256').toString('hex')}])
  memory.set('jiapu-data-v3:'+id,old)
  await activateSession(session());await importLegacyLocalAccount('旧账号','password1')
  assert.equal(store.members[0].name,'旧资料');assert.equal(store.session.accountId,'1');assert.equal(store.syncStatus,'synced')
  assert.deepEqual(memory.get('jiapu-data-v3:'+id),old);assert.ok(memory.has('family-import-previous:1:1'))
})
test('编辑成员不会重置已定制的自动提醒日历和提前时间', async () => {
  const {calls}=mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(o.method==='PUT')return ok(o,canonical(o));ok(o,response())})
  await activateSession(session())
  const first=await saveMember({name:'甲',relation:'本人',birthday:'1990-01-01',autoBirthday:true})
  await saveReminder({...store.reminders[0],title:'自定义生日',advance:'提前3天',calendar_type:'lunar'})
  await saveMember({...store.members[0],name:'改名甲',bio:'新生平',autoBirthday:true})
  assert.equal(store.reminders[0].id,`auto-birthday-${first.member.id}`)
  assert.equal(store.reminders[0].title,'自定义生日');assert.equal(store.reminders[0].calendar_type,'lunar');assert.equal(store.reminders[0].advance,'提前3天')
})
test('表单编辑时暂停自动拉取，迟到自动回包不推进基线', async () => {
  let held,hold=false
  const {calls}=mock(o=>{if(o.url.endsWith('/auth/me'))return me(o);if(hold&&o.url.includes('/family/sync')){held=o;return}ok(o,response())})
  await activateSession(session());store.editing=true
  const before=calls.length;await refreshFamily({automatic:true});assert.equal(calls.length,before)
  store.editing=false;hold=true;const refreshing=refreshFamily({automatic:true});await tick();store.editing=true
  ok(held,response({...empty(),profile:{name:'云端正在修改',avatar:''}},1,2));await refreshing
  assert.equal(store.revision,0);assert.equal(store.profile.name,'江氏家族');assert.equal(store.syncStatus,'synced')
  store.editing=false
})

test('进入访客模式会清理上一个账号的权限和同步状态', () => {
  store.role = 'VIEWER'
  store.revision = 42
  store.editing = true
  store.conflicts = ['members:a.bio']
  store.syncConflict = { local: empty(), remote: empty(), revision: 41 }
  store.notifications = [{ id: 1 }]
  store.error = '旧账号错误'
  store.syncStatus = 'conflict'

  enterGuest()

  assert.equal(store.guest, true)
  assert.equal(store.session?.accountId, 'guest')
  assert.equal(store.role, 'OWNER')
  assert.equal(store.revision, 0)
  assert.equal(store.editing, false)
  assert.deepEqual(store.conflicts, [])
  assert.equal(store.syncConflict, null)
  assert.deepEqual(store.notifications, [])
  assert.equal(store.error, '')
  assert.equal(store.syncStatus, 'idle')
})
