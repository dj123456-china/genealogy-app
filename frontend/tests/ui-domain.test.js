import test from 'node:test'
import assert from 'node:assert/strict'
import {relationshipPaths} from '../utils/tree-paths.js'
import {displayGeneration,analyzeNames,reminderViews,calendarDays} from '../utils/parity-domain.js'
import {nextOccurrence} from '../utils/dates.js'
const box=(left,top)=>({left,top,right:left+180,bottom:top+74,centerX:left+90,centerY:top+37})
test('个人家族只绘制录入的父母和配偶关系，并支持第 4 至 100 代',()=>{
  const members=[{id:'p',name:'父',gender:'男',generation:4},{id:'m',name:'母',gender:'女',generation:4,spouseId:'p'},{id:'c',name:'子',generation:5,parentIds:['p','m']},{id:'z',name:'后人',generation:100}]
  assert.equal(displayGeneration(members[3]),100)
  const paths=relationshipPaths({p:box(0,0),m:box(208,0),c:box(100,212),z:box(100,450)},members)
  assert.equal(paths.length,3)
  assert.deepEqual(paths.map(p=>p.kind).sort(),['parent','parent','spouse'])
  assert.ok(paths.every(p=>!p.d.includes('NaN')&&!p.description.includes('江')))
  assert.equal(relationshipPaths({p:box(0,0),m:box(208,0)},[{id:'p',name:'父'},{id:'m',name:'母'}]).length,0)
  assert.equal(analyzeNames(members,'父','子').estimated,false)
})
test('仅有称谓的两个旁系成员不展示未经录入的真实路径',()=>{
  const result=analyzeNames([{id:'self',name:'我',relation:'本人'},{id:'a',name:'叔',relation:'叔父'},{id:'b',name:'姑',relation:'姑母'}],'叔','姑')
  assert.equal(result.ok,false)
  assert.ok(!result.path)
})
test('纪念日时间线和月历遵循相同的农历与清明重复规则',()=>{
  const reminders=[{id:'lunar',date:'2025-01-29',calendar_type:'lunar',repeat:'每年',type:'birthday'},{id:'qingming',date:'2024-04-04',calendar_type:'qingming',repeat:'每年',type:'festival'}]
  const today=new Date(2026,0,1)
  assert.equal(nextOccurrence(reminders[0],today),'2026-02-17')
  assert.equal(reminderViews(reminders,today)[0].occurrence,'2026-02-17')
  assert.equal(calendarDays(2026,1,reminders).find(c=>c.date==='2026-02-17').type,'birthday')
  assert.equal(calendarDays(2026,3,reminders).find(c=>c.date==='2026-04-05').type,'festival')
})
test('同名成员按稳定 ID 核验，旧姓名输入不能默取第一人',()=>{
  const members=[{id:'parent',name:'同名',relation:'父亲',generation:2},{id:'child',name:'同名',relation:'子女',generation:4,parentIds:['parent']}]
  assert.equal(analyzeNames(members,'parent','child').title,'亲子关系')
  assert.equal(analyzeNames(members,'parent','child').estimated,false)
  assert.match(analyzeNames(members,'parent','child').headline,/第2代.*第4代/)
  assert.equal(analyzeNames(members,'同名','child').ok,false)
  assert.match(analyzeNames(members,'同名','child').message,/同名/)
  assert.equal(analyzeNames(members,'child','child').ok,false)
})
