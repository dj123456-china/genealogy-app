<template>
  <view class="login-page">
    <view class="login-card">
      <view class="login-story"><view class="login-brand"><text class="seal">谱</text><view><text class="section-title">家谱制作器</text><text class="description">宗谱档案管理</text></view></view><view class="story-copy"><text class="eyebrow">宗谱档案 · 本机典藏</text><view class="story-title"><text>一页家谱，</text><text>续写百年家史。</text></view><text class="story-desc">整理世系，记录生平与重要日子，
让家族记忆有迹可循。</text></view><text class="story-seal">敬宗
睦族</text></view>
      <view class="login-form">
        <text class="eyebrow">欢迎回来</text><text class="page-title">进入本机家谱</text><text class="description">已有账号直接登录，新登录名将自动注册。</text>
        <view class="login-fields"><view class="field"><text class="field-label">登录名</text><input v-model="username" class="control" maxlength="32" placeholder="请输入登录名" :disabled="busy" /></view><view class="field"><text class="field-label">密码</text><input v-model="password" class="control" password maxlength="64" placeholder="请输入至少 6 位密码" :disabled="busy" confirm-type="go" @confirm="submit" /></view></view>
        <view class="check-row"><switch :checked="remember" color="#8b2f2a" @change="remember = $event.detail.value" /><text>在此设备记住登录状态</text></view>
        <text v-if="error" class="error-text" role="alert">{{ error }}</text>
        <button class="btn primary full" :disabled="busy" :loading="busy" @click="submit">{{ busy ? '正在校验…' : '进入家谱' }}</button>
        <text class="login-note">账号和家谱仅保存在当前设备，不保存明文密码。不同本机账号分别保存资料，不支持云端同步；请勿使用常用密码。</text>
      </view>
    </view>
  </view>
</template>
<script setup>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { signInOrRegister } from '../../utils/auth.js'
import { store, activateSession } from '../../utils/store.js'
const username = ref(''), password = ref(''), remember = ref(true), busy = ref(false), error = ref('')
onShow(() => { error.value = store.error; if (store.session) uni.switchTab({ url: '/pages/home/index' }) })
async function submit() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { const session = await signInOrRegister(username.value, password.value); activateSession(session, remember.value); password.value = ''; uni.switchTab({ url: '/pages/home/index' }) }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
</script>
<style scoped>
.login-page { min-height: calc(100vh - 44px); display: flex; justify-content: center; align-items: center; padding: 40px 24px; }
.login-card { width: 960px; max-width: 100%; display: flex; border: 1px solid #cdc3ba; background: #f6f3ed; }
.login-story { width: 45%; position: relative; padding: 38px; background: #e2d8ca; border-right: 1px solid #cdc3ba; }
/* parity.css 为同名登录弹窗添加了装饰伪元素，滚动本页时会从卡片后方露出。 */
.login-page .login-story::before,
.login-page .login-story::after { content: none; display: none; }
.login-brand { display: flex; gap: 14px; align-items: center; }
.seal { background: #8b2f2a; color: #fffaf3; padding: 2px 12px; font-size: 32px; }
.story-copy { margin-top: 68px; }
.story-title { display: block; white-space: pre-line; font-size: 36px; line-height: 1.7; font-weight: 700; letter-spacing: 3px; }
.story-title text { display: block; }
.story-desc { display: block; white-space: pre-line; font-size: 14px; color: #6f645d; margin-top: 22px; line-height: 2; }
.story-seal { display: block; margin: 44px 0 0 auto; width: 52px; padding: 4px; text-align: center; white-space: pre-line; border: 2px solid #8b2f2a; color: #8b2f2a; line-height: 1.3; font-size: 20px; }
.login-form { flex: 1; padding: 44px; }
.login-fields { margin-top: 28px; }
.login-note { display: block; color: #6f645d; font-size: 12px; margin-top: 22px; line-height: 1.9; }
@media (max-width: 700px) { .login-page { padding: 20px 16px; align-items: flex-start; } .login-card { flex-direction: column; } .login-story { width: 100%; padding: 22px; border-right: 0; border-bottom: 1px solid #cdc3ba; } .story-copy { margin-top: 20px; } .story-title { font-size: 27px; line-height: 1.4; } .story-desc, .story-seal { display: none; } .login-form { padding: 26px 22px; } }
</style>
