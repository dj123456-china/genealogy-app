import { authenticatedRequest, store } from './store.js'
import { assetUrl } from './api.js'
const displayCache = new Map()
export async function readAvatarPayload(path) {
  let encoded, contentType, filename = 'avatar.jpg'
  if (typeof path === 'string' && path.startsWith('data:')) {
    const match = /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$/.exec(path)
    if (!match) throw Error('头像图片格式不正确。')
    contentType = match[1]; encoded = match[2]; filename = `avatar.${contentType.split('/')[1]}`
  }
  // #ifdef H5
  if (!encoded && typeof Blob !== 'undefined' && (path instanceof Blob || typeof window !== 'undefined')) {
    const blob = path instanceof Blob ? path : await (await fetch(path)).blob()
    if (!/^image\/(jpeg|png|webp)$/.test(blob.type)) throw Error('请选择 JPG、PNG 或 WEBP 图片。')
    if (blob.size > 2 * 1024 * 1024) throw Error('头像图片不能超过 2MB。')
    contentType = blob.type; filename = blob.name || `avatar.${blob.type.split('/')[1]}`
    encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(Error('头像读取失败。')); reader.readAsDataURL(blob) })
  }
  // #endif
  // #ifndef H5
  if (!encoded) {
    const ext = String(path).split('.').pop().toLowerCase()
    contentType = ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg'
    filename = `avatar.${ext}`
    if (typeof uni.getFileSystemManager === 'function') {
      encoded = await new Promise((resolve, reject) => uni.getFileSystemManager().readFile({ filePath: path, encoding: 'base64', success: r => resolve(r.data), fail: () => reject(Error('头像文件读取失败。')) }))
    } else if (typeof plus !== 'undefined') {
      encoded = await new Promise((resolve, reject) => plus.io.resolveLocalFileSystemURL(path, entry => entry.file(file => { const reader = new plus.io.FileReader(); reader.onloadend = e => resolve(e.target.result.split(',')[1]); reader.onerror = () => reject(Error('头像读取失败。')); reader.readAsDataURL(file) }, reject), reject))
    } else throw Error('当前平台不支持图片读取。')
  }
  // #endif
  if (!encoded || encoded.length > Math.ceil(2 * 1024 * 1024 / 3) * 4) throw Error('头像图片不能超过 2MB。')
  return { filename, content_type: contentType, data_base64: encoded }
}
export async function persistAvatar(path) {
  const account = store.session?.accountId, token = store.session?.accessToken, familyId = store.familyId
  const data = await readAvatarPayload(path)
  if (store.session?.accountId !== account || store.session?.accessToken !== token || store.familyId !== familyId) throw Error('账号或家族已切换，请重新选择头像。')
  const asset = await authenticatedRequest('/assets', { method: 'POST', data: { ...data, family_id: familyId } })
  return asset.url
}
export async function resolveAvatar(path) {
  if (!path || !path.startsWith('/api/assets/')) return path || ''
  const token = store.session?.accessToken
  const account = store.session?.accountId, familyId = store.familyId
  if (!token) return ''
  const key = `${store.session.accountId}:${path}`
  if (displayCache.has(key)) return displayCache.get(key)
  let result
  // #ifdef H5
  if (typeof window !== 'undefined') {
    const response = await fetch(assetUrl(path), { headers: { Authorization: `Bearer ${token}` } })
    if (!response.ok) throw Error('头像加载失败，请检查家族访问权限。')
    const blob = await response.blob()
    result = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob) })
  }
  // #endif
  // #ifndef H5
  if (!result) result = await new Promise((resolve, reject) => uni.downloadFile({ url: assetUrl(path), header: { Authorization: `Bearer ${token}` }, success: r => r.statusCode === 200 ? resolve(r.tempFilePath) : reject(Error('头像加载失败。')), fail: reject }))
  // #endif
  if (store.session?.accessToken !== token || store.session?.accountId !== account || store.familyId !== familyId) return ''
  displayCache.set(key, result)
  return result
}
export function clearAvatarCache() { displayCache.clear() }
