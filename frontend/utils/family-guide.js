import { ref, watch } from 'vue'
import { store, authenticatedRequest } from './store.js'
import { joinFamilyByCode, returnToPersonalFamily } from './family-sharing.js'
import { readStorage, writeStorage } from './storage.js'

const guideKey = () => `family-guide-settings:${store.session?.accountId}`
const guideIdentity = () => [store.session?.accountId,store.session?.accessToken].join('|')
async function saveGuidePreference(mode) {
  const id=guideIdentity(),key=guideKey()
  const settings=await authenticatedRequest('/auth/guides',{method:'PUT',data:{dismissal:mode}})
  if(id!==guideIdentity())throw Error('账号已切换，请重新操作。')
  writeStorage(key,settings)
  return settings
}
export async function getFamilyGuideSettings() {
  const id=guideIdentity(),key=guideKey()
  try {
    const settings=await authenticatedRequest('/auth/guides')
    if(id!==guideIdentity())throw Error('账号已切换，请重新操作。')
    writeStorage(key,settings);return settings
  }
  catch (error) {
    if (!error.network||id!==guideIdentity()) throw error
    const saved = readStorage(key)
    if (!saved) throw error
    const today = new Date(Date.now()+8*60*60*1000).toISOString().slice(0,10)
    return { ...saved, show_on_login: !saved.permanently_hidden && saved.dismissed_on !== today }
  }
}
export const dismissFamilyGuide = mode => {
  if (!['today', 'permanent'].includes(mode)) throw Error('请选择今日关闭或永久关闭。')
  return saveGuidePreference(mode)
}
export const restoreFamilyGuide = () => saveGuidePreference('reset')

// 同一个控制器供登录后的询问和“我的”中的手动导览使用。
export function createFamilyGuideFlow({ dialog, currentPage, notify = () => {}, onNavigate = () => {},
  getSettings = getFamilyGuideSettings, dismiss = dismissFamilyGuide, reset = restoreFamilyGuide,
  join = joinFamilyByCode, personal = returnToPersonalFamily,
  identity = () => [store.session?.accountId, store.session?.accessToken].join('|'),
  eligible = () => !!store.session?.accessToken && store.sessionValidated && !store.guest } = {}) {
  const familyGuideMode = ref(''), familyGuideBusy = ref(false), familyGuideError = ref(''),familyGuidePending=ref(false)
  let generation = 0, autoTour = true,pendingMode=''
  function assertCurrent(id, sequence) { if (id !== identity() || sequence !== generation) throw Error('账号已切换，请重新操作。') }
  function display(mode) { familyGuideMode.value = mode; familyGuideError.value = ''; dialog.value = 'familyGuide' }
  function requestDisplay(mode) {
    if(dialog.value && !['loginDialog','familyGuide'].includes(dialog.value)) {pendingMode=mode;familyGuidePending.value=true;return ''}
    pendingMode='';familyGuidePending.value=false;display(mode);return 'familyGuide'
  }
  watch(dialog,value=>{if(!value&&pendingMode){const mode=pendingMode;pendingMode='';familyGuidePending.value=false;display(mode)}},{flush:'sync'})
  async function beginLoginGuide({ method = 'account', restored = false } = {}) {
    if (!eligible()) return ''
    const id = identity(), sequence = ++generation
    familyGuideBusy.value = true; familyGuideError.value = ''
    try {
      const settings = await getSettings()
      assertCurrent(id, sequence); autoTour = !!settings.show_on_login
    } catch (error) {
      if (id !== identity() || sequence !== generation) return ''
      // 设置暂不可读取时仍保留入口；不会伪报已保存关闭偏好。
      autoTour = true
    } finally { if (id === identity() && sequence === generation) familyGuideBusy.value = false }
    if (id !== identity() || sequence !== generation) return ''
    if (method === 'phone' && !restored) return requestDisplay('invite')
    if (autoTour) return requestDisplay('tour')
    return ''
  }
  function finishSelection() {
    currentPage.value = 'account'
    if (autoTour) display('tour')
    else { familyGuideMode.value = ''; dialog.value = '' }
  }
  async function run(action, complete) {
    if (familyGuideBusy.value) return
    const id = identity(), sequence = generation
    familyGuideBusy.value = true; familyGuideError.value = ''
    try { const result = await action(); assertCurrent(id, sequence); complete(result) }
    catch (error) { if (id === identity() && sequence === generation) familyGuideError.value = error.message }
    finally { if (id === identity() && sequence === generation) familyGuideBusy.value = false }
  }
  const joinFromLogin = code => run(() => join(code), result => { notify(result?.synced===false?'已加入家族，资料尚未同步。请处理页面的同步状态。':'已加入家族家谱，可在“我的”返回自己的家谱。'); finishSelection() })
  const enterPersonalFromLogin = () => run(personal, result => { notify(result?.synced===false?'已进入自己的家谱，资料尚未同步。请处理页面的同步状态。':'已进入自己的家谱。'); finishSelection() })
  function openFamilyGuides() { if (!eligible()) { notify('请先登录后查看导览。'); return }; generation++;pendingMode='';familyGuidePending.value=false; familyGuideBusy.value = false; display('library') }
  function closeFamilyGuide() { if (familyGuideBusy.value) return; familyGuideMode.value = ''; if (dialog.value === 'familyGuide') dialog.value = '' }
  const dismissGuide = mode => run(() => dismiss(mode), () => { autoTour = false; closeFamilyGuideAfterRun(); notify(mode === 'today' ? '今天登录不再显示导览，明天恢复。' : '已永久关闭自动导览，仍可在“我的”查看。') })
  function closeFamilyGuideAfterRun() { familyGuideMode.value = ''; dialog.value = '' }
  const restoreGuide = () => run(reset, () => { autoTour = true; notify('已恢复每次登录显示导览。'); display('library') })
  function guideNavigate(action) { if (familyGuideBusy.value) return; closeFamilyGuide(); currentPage.value = 'account'; onNavigate(action) }
  function clearFamilyGuide() { generation++;pendingMode='';familyGuidePending.value=false; familyGuideMode.value = ''; familyGuideBusy.value = false; familyGuideError.value = ''; if (dialog.value === 'familyGuide') dialog.value = '' }
  return { familyGuideMode, familyGuideBusy, familyGuideError,familyGuidePending, beginLoginGuide, openFamilyGuides, closeFamilyGuide, joinFromLogin, enterPersonalFromLogin, dismissGuide, restoreGuide, guideNavigate, clearFamilyGuide }
}
