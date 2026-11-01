// H5 同机调试走当前电脑；手机运行时使用开发电脑的局域网地址。
// 更换网络后，可通过 uni.setStorageSync('family-api-base-url', 'http://电脑IP:8000/api') 覆盖。
const DEFAULT_API_BASE_URL = 'http://172.16.96.98:8000/api'
export const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || (typeof window !== 'undefined' && typeof plus === 'undefined' && window.location?.hostname
  ? `${window.location.protocol}//${window.location.hostname}:8000/api`
  : DEFAULT_API_BASE_URL
)

export function baseUrl() {
  const override = typeof uni.getStorageSync === 'function' ? uni.getStorageSync('family-api-base-url') : ''
  return typeof override === 'string' && /^https?:\/\/[^/]+\/api\/?$/.test(override)
    ? override.replace(/\/$/, '')
    : API_BASE_URL
}

function errorMessage(payload, fallback) {
  if (typeof payload?.detail === 'string') return payload.detail
  if (typeof payload?.detail?.message === 'string') return payload.detail.message
  if (Array.isArray(payload?.detail)) {
    const fields = payload.detail.map(item => item.loc?.[item.loc.length - 1])
    if (fields.includes('phone')) return '手机号格式不正确'
    if (fields.includes('sms_code')) return '请输入 6 位短信验证码'
    if (fields.includes('scene')) return '短信场景不支持'
    if (fields.includes('password') || fields.includes('new_password')) return '密码须为 6 至 64 位'
    if (fields.includes('death_year')) return '卒年格式不正确，请输入四位年份'
    return '请检查输入内容后重试'
  }
  return typeof payload?.message === 'string' ? payload.message : fallback
}

export function assetUrl(path) {
  if (/^https?:\/\//.test(path)) return path
  return baseUrl().replace(/\/api$/, '') + path
}

export function request(path, { method = 'GET', data, token, timeout = 15000 } = {}) {
  return new Promise((resolve, reject) => {
    if (typeof uni.request !== 'function') {
      reject(new Error('当前运行环境不支持网络请求。'))
      return
    }
    uni.request({
      url: `${baseUrl()}${path}`,
      method,
      data,
      timeout,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      success: response => {
        const payload = response.data
        if (response.statusCode >= 200 && response.statusCode < 300) resolve(payload)
        else {
          const error = new Error(errorMessage(payload, `请求失败（${response.statusCode}）`))
          error.status = response.statusCode
          error.details = payload?.detail
          reject(error)
        }
      },
      fail: failure => {
        const detail = typeof failure?.errMsg === 'string' && failure.errMsg.trim() ? `（${failure.errMsg.trim()}）` : ''
        const error = new Error(`无法连接服务器${detail}，资料已保留在本机，请检查后端是否启动及 API 地址。`)
        error.network = true
        error.cause = failure
        reject(error)
      }
    })
  })
}
