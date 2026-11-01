// 三方合并：保留本机变更，只合并未冲突的云端变更。
export const clone = value => JSON.parse(JSON.stringify(value))
function equal(a, b) {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false
  if (Array.isArray(a) !== Array.isArray(b)) return false
  const keys = Object.keys(a), others = Object.keys(b)
  return keys.length === others.length && keys.every(k => Object.hasOwn(b, k) && equal(a[k], b[k]))
}
function field(base, local, remote, path, conflicts) {
  if (equal(local, remote)) return cloneValue(local)
  if (equal(local, base)) return cloneValue(remote)
  if (equal(remote, base)) return cloneValue(local)
  conflicts.push(path)
  return cloneValue(local)
}
const cloneValue = v => v === undefined ? undefined : clone(v)
function entity(base, local, remote, path, conflicts) {
  if (!base || !local || !remote) return field(base, local, remote, path, conflicts)
  const result = {}
  const keys = new Set([...Object.keys(base), ...Object.keys(local), ...Object.keys(remote)])
  if (path.startsWith('members:') && keys.has('parentRoles')) {
    // 父母编号和角色必须来自同一端，避免合并后把母亲编号配成父亲。
    const parents = item => ({ parentIds: item.parentIds || [], parentRoles: item.parentRoles || [] })
    Object.assign(result, field(parents(base), parents(local), parents(remote), `${path}.parentIds`, conflicts))
    keys.delete('parentIds'); keys.delete('parentRoles')
  }
  for (const key of keys) {
    const value = field(base[key], local[key], remote[key], `${path}.${key}`, conflicts)
    if (value !== undefined) result[key] = value
  }
  return result
}
function collection(base, local, remote, name, conflicts) {
  const maps = [base, local, remote].map(list => new Map((list || []).map(item => [String(item.id), item])))
  const ids = new Set([...maps[1].keys(), ...maps[2].keys(), ...maps[0].keys()])
  return [...ids].map(id => entity(...maps.map(m => m.get(id)), `${name}:${id}`, conflicts)).filter(Boolean)
}
export function mergeFamily(base, local, remote) {
  const conflicts = []
  const data = {
    profile: entity(base.profile, local.profile, remote.profile, 'profile', conflicts),
    members: collection(base.members, local.members, remote.members, 'members', conflicts),
    reminders: collection(base.reminders, local.reminders, remote.reminders, 'reminders', conflicts)
  }
  return { data, conflicts }
}
export function sameFamily(a, b) { return equal(a, b) }
