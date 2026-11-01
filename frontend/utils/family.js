import { parseDate } from './dates.js'
export const RELATIONS = ['本人', '配偶', '父亲', '母亲', '祖父', '祖母', '外祖父', '外祖母', '兄弟', '姐妹', '子女', '叔父', '姑母', '其他亲属']
const MALE_RELATIONS = new Set(['父亲', '祖父', '外祖父', '叔父'])
const FEMALE_RELATIONS = new Set(['母亲', '祖母', '外祖母', '姑母'])
export function genderFor(relation) {
  if (MALE_RELATIONS.has(relation)) return '男'
  if (FEMALE_RELATIONS.has(relation)) return '女'
  return '未知'
}
export function generationFor(relation, members = [], parentIds = []) {
  const parentGenerations = parentIds
    .map(id => members.find(member => String(member.id) === String(id))?.generation)
    .filter(value => Number.isInteger(Number(value)))
    .map(Number)
  if (parentGenerations.length) return Math.min(100, Math.max(...parentGenerations) + 1)
  if (/祖/.test(relation)) return 1
  if (/父|母|叔|姑/.test(relation)) return 2
  if (relation === '子女') return 4
  return 3
}
// 新档案明确保存父母角色；旧档案优先按已登记性别辨认，再兼容原有顺序。
export function parentLinks(member, members = []) {
  const ids = member.parentIds || [], roles = member.parentRoles || []
  if (roles.length === ids.length) return ids.map((id, i) => ({ id, role: roles[i] }))
  const links = ids.map(id => ({ id, role: '' })), used = new Set()
  for (const link of links) {
    const gender = members.find(m => m.id === link.id)?.gender
    const role = gender === '男' ? 'father' : gender === '女' ? 'mother' : ''
    if (role && !used.has(role)) { link.role = role; used.add(role) }
  }
  for (const link of links) {
    if (!link.role) { link.role = used.has('father') ? 'mother' : 'father'; used.add(link.role) }
  }
  return links
}
export function parentFields(member, members = []) {
  const links = parentLinks(member, members)
  const father = links.find(link => link.role === 'father'), mother = links.find(link => link.role === 'mother')
  const unspecified = links.filter(link => link.role === 'parent')
  return { parentOne: father?.id || unspecified.shift()?.id || '', parentTwo: mother?.id || unspecified.shift()?.id || '' }
}
export function formParentLinks(form) {
  const links = [{ id: form.parentOne, role: 'father' }, { id: form.parentTwo, role: 'mother' }].filter(link => link.id)
  return { parentIds: links.map(link => link.id), parentRoles: links.map(link => link.role) }
}
export function validateMember(member, members, today) {
  if (!member.name?.trim() || member.name.trim().length > 64) throw new Error('请填写 1 至 64 个字的姓名。')
  if (member.relation === '本人' && members.some(m => m.id !== member.id && m.relation === '本人')) throw new Error('已存在“本人”，请修改成员关系。')
  if (!member.relation?.trim() || member.relation.length > 32) throw new Error('请选择或填写与本人的关系。')
  if (member.gender && !['男', '女', '未知'].includes(member.gender)) throw new Error('性别格式不正确。')
  if (member.generation != null && (!Number.isInteger(member.generation) || member.generation < 1 || member.generation > 100)) throw new Error('世代须为 1 至 100。')
  if (member.birthday && !parseDate(member.birthday)) throw new Error('出生日期无效。')
  if (member.birthYear != null && member.birthday && Number(member.birthYear) !== Number(member.birthday.slice(0, 4))) throw new Error('出生年份与出生日期不一致。')
  if (member.deathDate && (!parseDate(member.deathDate) || member.deathDate > today || (member.birthday && member.deathDate < member.birthday) || (member.deathYear && String(member.deathYear) !== member.deathDate.slice(0, 4)))) throw new Error('忌日与生卒资料不一致。')
  if (member.birthday && member.birthday > today) throw new Error('出生日期不能晚于今天。')
  const birthYear = Number((member.birthday || '').slice(0, 4))
  if (member.deathYear && (!/^\d{4}$/.test(String(member.deathYear)) || +member.deathYear < (birthYear || 1000) || +member.deathYear > +today.slice(0, 4))) throw new Error('卒年应在出生年份与当前年份之间。')
  const parents = member.parentIds || []
  if (parents.length > 2 || new Set(parents).size !== parents.length) throw new Error('最多选择两位不同的父母。')
  const roles = member.parentRoles || []
  if (!Array.isArray(roles) || (roles.length && (roles.length !== parents.length || roles.some(role => !['father', 'mother', 'parent'].includes(role)) || ['father', 'mother'].some(role => roles.filter(value => value === role).length > 1)))) throw new Error('父母关联角色不正确，请重新选择父亲和母亲。')
  if (parents.includes(member.id) || member.spouseId === member.id) throw new Error('成员不能与自己建立亲属关系。')
  if (member.spouseId && parents.includes(member.spouseId)) throw new Error('父母和配偶不能是同一位成员。')
  if (parents.some(id => !members.some(m => m.id === id)) || (member.spouseId && !members.some(m => m.id === member.spouseId))) throw new Error('关联成员已不存在，请重新选择。')
  const datedParents = parents.map(id => members.find(m => m.id === id)).filter(parent => parent?.birthday && member.birthday)
  if (datedParents.some(parent => member.birthday <= parent.birthday)) throw new Error('成员出生日期不能早于或等于父母。')
  const spouse = members.find(m => m.id === member.spouseId)
  if (spouse?.spouseId && spouse.spouseId !== member.id) throw new Error('所选成员已有配偶，请先修改原有关系。')
  const all = [...members.filter(m => m.id !== member.id), member]
  function hasAncestor(id, target, seen = new Set()) {
    if (id === target) return true
    if (seen.has(id)) return false
    seen.add(id)
    return (all.find(m => m.id === id)?.parentIds || []).some(p => hasAncestor(p, target, seen))
  }
  if (parents.some(id => hasAncestor(id, member.id))) throw new Error('该关系会形成循环世系，请检查父母信息。')
  for (const item of all) {
    if (item.spouseId && (hasAncestor(item.id, item.spouseId) || hasAncestor(item.spouseId, item.id))) throw new Error('直系祖先或后代不能设置为配偶。')
  }
  return true
}
export function familyEdges(members) {
  const ids = new Set(members.map(m => m.id)), result = [], known = new Set()
  const add = e => { const key = e.kind + [e.from, e.to].sort().join(':'); if (!known.has(key)) { known.add(key); result.push(e) } }
  members.forEach(m => {
    ;(m.parentIds || []).forEach(p => { if (ids.has(p)) add({ from: p, to: m.id, kind: 'parent' }) })
    if (ids.has(m.spouseId)) add({ from: m.id, to: m.spouseId, kind: 'spouse' })
  })
  return result
}
export function analyzeRelationship(members, idA, idB) {
  const a = members.find(m => m.id === idA), b = members.find(m => m.id === idB)
  if (!a || !b) return { ok: false, message: '请选择两位已录入的成员。' }
  if (idA === idB) return { ok: false, message: '请选择两位不同的成员。' }
  const graph = new Map(members.map(m => [m.id, []]))
  familyEdges(members).forEach(e => {
    graph.get(e.from).push({ to: e.to, kind: e.kind, direction: 'down' })
    graph.get(e.to).push({ to: e.from, kind: e.kind, direction: 'up' })
  })
  const queue = [{ id: idA, names: [a.name], edges: [] }], seen = new Set([idA])
  while (queue.length) {
    const cur = queue.shift()
    for (const edge of graph.get(cur.id)) {
      if (seen.has(edge.to)) continue
      const next = { id: edge.to, names: [...cur.names, members.find(m => m.id === edge.to).name], edges: [...cur.edges, edge] }
      if (edge.to === idB) {
        const path = next.edges
        let title = '存在族谱关联'
        if (path.length === 1) title = edge.kind === 'spouse' ? '夫妻关系' : '亲子关系'
        else if (path.every(e => e.kind === 'parent' && e.direction === path[0].direction)) title = path.length === 2 ? '祖孙关系' : '直系祖孙关系'
        else if (path.length === 2 && path.every(e => e.kind === 'parent') && path[0].direction === 'up' && path[1].direction === 'down') title = '兄弟姐妹关系'
        else if (path.some(e => e.kind === 'spouse')) title = '姻亲关系'
        return { ok: true, title, message: `${a.name} 与 ${b.name}：${title}`, path: next.names.join(' → '), detail: '依据已填写的父母、配偶关联。' }
      }
      seen.add(edge.to); queue.push(next)
    }
  }
  const self = a.relation === '本人' ? a : b.relation === '本人' ? b : null
  if (self) {
    const other = self.id === a.id ? b : a
    return { ok: true, title: '已登记的亲属称谓', message: `${other.name} 登记为 ${self.name} 的${other.relation}`, detail: '来自“与我的关系”字段；可补充父母、配偶以建立完整关系路径。' }
  }
  return { ok: false, message: '资料不足，尚未找到关系路径。请在成员资料中补充父母或配偶。' }
}
export function inferYears(a, b, year = new Date().getFullYear()) {
  if (![a, b].every(v => /^\d{4}$/.test(String(v)) && +v >= 1000 && +v <= year)) return { ok: false, message: `请输入 1000—${year} 之间的出生年份。` }
  const difference = Math.abs(+a - +b)
  return { ok: true, message: `相差 ${difference} 年：${difference >= 45 ? '可能为祖辈与晚辈' : difference >= 22 ? '可能为父辈与子女' : difference <= 15 ? '可能为同辈或配偶' : '年龄差不足以判断'}`, detail: '仅依据年龄差推测，不能确认真实亲属关系。' }
}
export const DEMO_MEMBERS = [
  { id: 'd1', name: '江守诚', relation: '祖父', generation: 1, gender: '男', spouseId: 'd2', birthday: '1940-03-12' },
  { id: 'd2', name: '林秀兰', relation: '祖母', generation: 1, gender: '女', spouseId: 'd1' },
  { id: 'd3', name: '江建国', relation: '父亲', generation: 2, parentIds: ['d1', 'd2'] },
  { id: 'd4', name: '江建民', relation: '叔父', generation: 2, parentIds: ['d1', 'd2'] },
  { id: 'd5', name: '江建芳', relation: '姑母', generation: 2, parentIds: ['d1', 'd2'] },
  { id: 'd6', name: '江宇航', relation: '本人', generation: 3, parentIds: ['d3'] },
  { id: 'd7', name: '江思宁', relation: '姐妹', generation: 3, parentIds: ['d3'] }
]
