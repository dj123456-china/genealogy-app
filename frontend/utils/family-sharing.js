import { store, authenticatedRequest, switchFamily, selectPersonalFamily, joinFamilyByCode as joinByCode } from './store.js'

export const normalizeInviteCode = value => String(value || '').trim().normalize('NFKC')
export function validateInviteCode(value) {
  const code = normalizeInviteCode(value)
  if (!/^\d{6}$/.test(code)) throw Error('请输入 6 位数字邀请码，与短信验证码不同。')
  return code
}
export const listFamilies = () => authenticatedRequest('/family/list')
export const listInviteCodes = () => authenticatedRequest('/family/invite-codes')
export function createInviteCode(role = 'VIEWER') {
  if (!['VIEWER', 'EDITOR'].includes(role)) throw Error('请选择只读或可编辑权限。')
  return authenticatedRequest('/family/invite-codes', { method: 'POST', data: { role } })
}
export const revokeInviteCode = id => authenticatedRequest(`/family/invite-codes/${id}`, { method: 'DELETE' })
export const joinFamilyByCode = code => joinByCode(validateInviteCode(code))
export async function returnToPersonalFamily() {
  const families = await listFamilies()
  const personal = families.find(family => Number(family.owner_id) === Number(store.user?.id))
  if (!personal) return selectPersonalFamily()
  return Number(personal.id) === Number(store.familyId) ? { synced: store.syncStatus === 'synced' } : switchFamily(personal.id)
}
