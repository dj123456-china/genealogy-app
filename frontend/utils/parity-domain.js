import lunar from 'lunar-javascript'
import { parseDate, dateString, nextOccurrence, countdown, dayDistance, remindersForDate } from './dates.js'
import { analyzeRelationship as explicitRelationship, generationFor } from './family.js'
export const demoMembers = [
  {name:'江守诚',relation:'祖父',birthYear:1940,generation:1,gender:'男',image:'/static/assets/avatar-grandfather.jpg'},
  {name:'林秀兰',relation:'祖母',birthYear:1942,generation:1,gender:'女',image:'/static/assets/avatar-grandmother.jpg'},
  {name:'江建国',relation:'父亲',birthYear:1965,generation:2,gender:'男'},
  {name:'江建民',relation:'叔父',birthYear:1968,generation:2,gender:'男'},
  {name:'江建芳',relation:'姑母',birthYear:1970,generation:2,gender:'女'},
  {name:'江宇航',relation:'本人',birthYear:1992,generation:3,gender:'男'},
  {name:'江思宁',relation:'妹妹',birthYear:1995,generation:3,gender:'女'}
].map((m,i)=>({...m,id:'demo-'+i}))
export const demoEdges = [
  {a:'江守诚',b:'林秀兰',kind:'spouse'},
  ...['江建国','江建民','江建芳'].flatMap(child=>['江守诚','林秀兰'].map(parent=>({parent,child}))),
  ...['江宇航','江思宁'].map(child=>({parent:'江建国',child})),
  ...[['江建国','江建民'],['江建国','江建芳'],['江建民','江建芳'],['江宇航','江思宁']].map(([a,b])=>({a,b,kind:'sibling'}))
]
// 首页、时间线均只展示当前账号保存的提醒。
export function reminderViews(reminders, today = new Date()) {
  return reminders.filter(r => parseDate(r.date)).map(r => {
    const occurrence = nextOccurrence(r, today)
    return { ...r, occurrence, days: dayDistance(occurrence, today),
      displayDate: occurrence?occurrence.replace(/-/g, ' / '):'待下次有效日期', countdown: countdown(occurrence, today),
      description: [({birthday:'生日',memorial:'忌日',festival:'传统祭日'})[r.type] || r.type, r.member ? '相关人员：' + r.member : ''].filter(Boolean).join('，'),
      tag: ({solar:'公历',lunar:'农历',qingming:'清明节气'})[r.calendar_type || 'solar'] + ' · ' + (typeof r.advance === 'number' ? (r.advance ? '提前 ' + r.advance + ' 天' : '当天') : r.advance || '当天') + '提醒'
    }
  }).sort((a,b) => (a.occurrence||'9999').localeCompare(b.occurrence||'9999'))
}
export const displayGeneration = m => Math.min(100,Math.max(1,Number(m.generation)||generationFor(m.relation)))
export function lunarInfo(value) {
  const d=typeof value==='string'?parseDate(value):value
  if(!d) return {short:'',full:'',monthKey:''}
  const l=lunar.Solar.fromYmd(d.getFullYear(),d.getMonth()+1,d.getDate()).getLunar()
  const month=l.getMonthInChinese()+'月', day=l.getDayInChinese(), monthKey=l.getYearInGanZhi()+'年'+month
  return {short:month+day,full:monthKey+day,monthKey}
}
export function calendarDays(year,month,reminders,today=dateString()) {
  const offset=(new Date(year,month,1).getDay()+6)%7, days=new Date(year,month+1,0).getDate()
  return Array.from({length:offset+days>35?42:35},(_,i)=>{
    const d=new Date(year,month,i-offset+1,12), date=dateString(d), l=lunarInfo(d)
    const type=remindersForDate(reminders,date)[0]?.type
    return {date,day:d.getDate(),muted:d.getMonth()!==month,today:date===today,lunar:l.short,type,label:`${d.getFullYear()} 年 ${d.getMonth()+1} 月 ${d.getDate()} 日，农历${l.full}${type?'，有纪念日提醒':''}`}
  })
}
export function inferRelationshipByYears(yearA,yearB,year=new Date().getFullYear()) {
  const a=String(yearA||'').trim(),b=String(yearB||'').trim()
  if(![a,b].every(v=>/^\d{4}$/.test(v)&&+v>=1000&&+v<=year))return {ok:false,message:`请输入 1000-${year} 之间的四位出生年份。`}
  if(a===b)return {ok:true,estimated:true,title:'可能为同辈或年龄相近成员',headline:`出生年份相同（${a} 年）`,detail:'仅按出生年份推测，不能确认真实亲属关系。'}
  const diff=Math.abs(+a-+b),title=diff>=45?'可能为祖辈与晚辈':diff>=22?'可能为父辈与子女':diff<=15?'可能为同辈或配偶':'年龄差不足以判断'
  return {ok:true,estimated:true,title,headline:`相差 ${diff} 年：${title}`,detail:'推测依据：两人的出生年份差；这不是已录入的族谱关系。'}
}
export function memberLabel(member, members = []) {
  if (!member) return '未选择成员'
  let label = `${member.name} · ${member.relation || '家族成员'} · 第${displayGeneration(member)}代`
  if (members.filter(m => m.name === member.name).length > 1) label += `${member.birthday ? ' · '+member.birthday : ''} · 档案${String(member.id).slice(-6)}`
  return label
}
export function analyzeNames(members,rawA,rawB) {
  const a=String(rawA||'').trim(),b=String(rawB||'').trim()
  if(!a||!b)return {ok:false,message:'请选择两位成员。'}
  const resolve=value=>{
    const byId=members.find(m=>String(m.id)===value)
    if(byId)return {member:byId}
    const byName=members.filter(m=>m.name===value)
    if(byName.length>1)return {error:'存在同名成员，请从列表选择具体成员，不能仅凭姓名分析。'}
    return byName.length===1?{member:byName[0]}:{error:'仅支持已录入族谱的成员，请从列表中选择。'}
  }
  const first=resolve(a),second=resolve(b)
  if(first.error||second.error)return {ok:false,message:first.error||second.error}
  const ma=first.member,mb=second.member
  if(ma.id===mb.id)return {ok:false,message:'请选择两位不同的成员。'}
  const exact=explicitRelationship(members,ma.id,mb.id)
  const labelA=memberLabel(ma,members),labelB=memberLabel(mb,members)
  if(exact.ok&&exact.path)return {...exact,estimated:false,headline:`${labelA} 与 ${labelB}：${exact.title}`}
  return {...exact,estimated:true,headline:exact.message||'',detail:exact.detail||'请补充父母和配偶关联。'}
}
