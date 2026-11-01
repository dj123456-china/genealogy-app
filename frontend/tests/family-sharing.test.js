import test from 'node:test'
import assert from 'node:assert/strict'
import { ref } from 'vue'
import { createFamilyGuideFlow } from '../utils/family-guide.js'
import { validateInviteCode, returnToPersonalFamily } from '../utils/family-sharing.js'
import { store, activateSession, joinFamilyByCode, saveMember, enterGuest } from '../utils/store.js'

function guide(overrides = {}) {
  const dialog = ref(''), currentPage = ref('home'), calls = [], notifications = []
  const flow = createFamilyGuideFlow({dialog,currentPage,eligible:()=>true,identity:()=> 'test-account',
    getSettings:async()=>({show_on_login:true}),join:async code=>calls.push(['join',code]),personal:async()=>calls.push(['personal']),
    dismiss:async mode=>calls.push(['dismiss',mode]),reset:async()=>calls.push(['reset']),notify:message=>notifications.push(message),...overrides})
  return {...flow,dialog,currentPage,calls,notifications}
}

test('邀请码保留前导零，接受全角数字并拒绝短信以外的错误长度',()=>{
  assert.equal(validateInviteCode(' ０１２３４５ '),'012345')
  for(const value of ['12345','1234567','12a456','']) assert.throws(()=>validateInviteCode(value),/6 位数字/)
})
test('手机号登录询问邀请码，无码进入自己的家谱再显示导览',async()=>{
  const flow=guide()
  assert.equal(await flow.beginLoginGuide({method:'phone'}),'familyGuide')
  assert.equal(flow.familyGuideMode.value,'invite')
  await flow.enterPersonalFromLogin()
  assert.deepEqual(flow.calls,[['personal']])
  assert.equal(flow.currentPage.value,'account')
  assert.equal(flow.familyGuideMode.value,'tour')
})
test('已永久关闭导览的手机号登录仍可输入邀请码加入；账号登录不自动弹导览',async()=>{
  const flow=guide({getSettings:async()=>({show_on_login:false})})
  await flow.beginLoginGuide({method:'phone'})
  assert.equal(flow.familyGuideMode.value,'invite')
  await flow.joinFromLogin('012345')
  assert.deepEqual(flow.calls,[['join','012345']])
  assert.equal(flow.dialog.value,'')
  assert.equal(await flow.beginLoginGuide({method:'account'}),'')
  flow.openFamilyGuides()
  assert.equal(flow.familyGuideMode.value,'library')
  await flow.restoreGuide()
  assert.deepEqual(flow.calls.at(-1),['reset'])
})
test('今日关闭确实写设置；保存失败保持导览与错误可见',async()=>{
  const flow=guide()
  await flow.beginLoginGuide()
  await flow.dismissGuide('today')
  assert.deepEqual(flow.calls,[['dismiss','today']])
  assert.equal(flow.dialog.value,'')
  const failed=guide({dismiss:async()=>{throw Error('服务器不可用')}})
  await failed.beginLoginGuide()
  await failed.dismissGuide('permanent')
  assert.equal(failed.dialog.value,'familyGuide')
  assert.equal(failed.familyGuideError.value,'服务器不可用')
})
test('导览设置的迟到旧账号响应不能给新账号弹窗',async()=>{
  let user='old',respond
  const flow=guide({identity:()=>user,getSettings:()=>new Promise(resolve=>respond=resolve)})
  const pending=flow.beginLoginGuide({method:'phone'})
  user='new';flow.clearFamilyGuide();respond({show_on_login:true})
  assert.equal(await pending,'')
  assert.equal(flow.dialog.value,'')
  assert.equal(flow.familyGuideBusy.value,false)
})
test('恢复时迟到导览等待当前编辑弹窗关闭，不覆盖未保存表单',async()=>{
  let respond
  const flow=guide({getSettings:()=>new Promise(resolve=>respond=resolve)})
  const pending=flow.beginLoginGuide({restored:true})
  flow.dialog.value='memberDialogForm'
  respond({show_on_login:true})
  assert.equal(await pending,'')
  assert.equal(flow.dialog.value,'memberDialogForm')
  assert.equal(flow.familyGuidePending.value,true)
  flow.dialog.value=''
  assert.equal(flow.dialog.value,'familyGuide')
  assert.equal(flow.familyGuideMode.value,'tour')
  assert.equal(flow.familyGuidePending.value,false)
})
test('加入后仍有同步冲突时如实说明状态',async()=>{
  const flow=guide({join:async()=>({synced:false})})
  await flow.beginLoginGuide({method:'phone'})
  await flow.joinFromLogin('012345')
  assert.match(flow.notifications[0],/尚未同步/)
})

const snapshot=(id,role,members=[])=>({family_id:id,revision:0,role,profile:{name:id===1?'我的家谱':'受邀家谱',avatar:''},members,reminders:[]})
const member={id:1,client_id:'personal-person',name:'本人',relation:'本人',gender:'男',generation:3,parent_ids:[],parent_roles:[]}
function device(handler) {
  const memory=new Map(),calls=[]
  globalThis.uni={getStorageSync:key=>memory.get(key)||'',setStorageSync:(key,value)=>memory.set(key,structuredClone(value)),removeStorageSync:key=>memory.delete(key),request:options=>{calls.push(options);handler(options)}}
  return calls
}
const reply=(options,data)=>options.success({statusCode:200,data})
const session={authVersion:2,accountId:'1',username:'本人',accessToken:'token1',user:{id:1,username:'本人',active_family_id:1}}
test('邀请码加入使用独立云家谱和只读权限；返回自己谱仍保留原成员',async()=>{
  const calls=device(options=>{
    if(options.url.endsWith('/auth/me'))return reply(options,session.user)
    if(options.url.endsWith('/family/list'))return reply(options,[{id:1,owner_id:1,role:'OWNER',active:true},{id:2,owner_id:2,role:'VIEWER',active:false}])
    if(options.url.endsWith('/join-by-code'))return reply(options,snapshot(2,'VIEWER'))
    if(options.url.endsWith('/family/active'))return reply(options,snapshot(options.data.family_id,'OWNER',[member]))
    return reply(options,snapshot(1,'OWNER',[member]))
  })
  await activateSession(session)
  await joinFamilyByCode('012345')
  assert.equal(store.familyId,2)
  assert.equal(store.role,'VIEWER')
  assert.equal(store.members.length,0)
  assert.deepEqual(calls.find(call=>call.url.endsWith('/join-by-code')).data,{code:'012345'})
  await assert.rejects(saveMember({name:'禁止编辑',relation:'其他亲属'}),/查看权限/)
  await returnToPersonalFamily()
  assert.equal(store.familyId,1)
  assert.equal(store.members[0].id,'personal-person')
})
test('离线待同步时不消费邀请码，账号切换后的加入回包不会覆盖新身份',async()=>{
  let online=true,held
  const calls=device(options=>{
    if(options.url.endsWith('/auth/me'))return reply(options,session.user)
    if(options.url.endsWith('/family/list'))return reply(options,[{id:1,owner_id:1,role:'OWNER',active:true}])
    if(options.url.endsWith('/join-by-code')){held=options;return}
    if(!online)return options.fail()
    reply(options,snapshot(1,'OWNER',[member]))
  })
  await activateSession(session);online=false
  await saveMember({name:'离线成员',relation:'其他亲属'})
  await assert.rejects(joinFamilyByCode('012345'),/未同步/)
  assert.equal(calls.filter(call=>call.url.endsWith('/join-by-code')).length,0)
  online=true
  // 新设备无待提交，模拟另一份本机缓存。
  device(options=>{
    if(options.url.endsWith('/auth/me'))return reply(options,session.user)
    if(options.url.endsWith('/family/list'))return reply(options,[{id:1,owner_id:1,role:'OWNER',active:true}])
    if(options.url.endsWith('/join-by-code')){held=options;return}
    reply(options,snapshot(1,'OWNER',[member]))
  })
  await activateSession(session)
  const pending=joinFamilyByCode('012345');enterGuest();reply(held,snapshot(2,'EDITOR'))
  await assert.rejects(pending,/切换/)
  assert.equal(store.guest,true)
  assert.equal(store.familyId,null)
})

test('手动打开所有导览取消待弹的自动导览，关闭后不重复弹出',async()=>{
  const flow=guide()
  flow.dialog.value='memberDialogForm'
  await flow.beginLoginGuide({restored:true})
  assert.equal(flow.familyGuidePending.value,true)
  flow.openFamilyGuides()
  assert.equal(flow.familyGuideMode.value,'library')
  assert.equal(flow.familyGuidePending.value,false)
  flow.closeFamilyGuide()
  assert.equal(flow.dialog.value,'')
})
