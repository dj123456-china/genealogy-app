// uni 存储兼容 App、Web、小程序，并兼容旧网页保存的 JSON 字符串。
export function readStorage(key, fallback = null) {
  const value = uni.getStorageSync(key)
  if (value === '' || value === undefined || value === null) return fallback
  if (typeof value === 'string') {
    try { return JSON.parse(value) } catch { return value }
  }
  return value
}
export function writeStorage(key, value) {
  try { uni.setStorageSync(key, value) }
  catch { throw new Error('保存失败，请检查设备存储空间后重试。') }
}
export function uid() {
  // 标识符和密码盐只需要唯一性；不作为登录令牌或加密密钥。
  return Date.now().toString(16).padStart(12, '0') + Array.from({ length: 20 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}
