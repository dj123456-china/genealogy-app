<template>
  <view v-if="store.session" class="page-wrap form-page"><PageHeading eyebrow="账户资料" title="自定义头像与名称" /><view class="panel"><view class="avatar-editor"><MemberAvatar :name="name" :label="name.slice(0, 1)" :src="avatar" large /><view><button class="btn" :disabled="busy" @click="chooseAvatar">选择头像</button><button class="link" @click="avatar = ''">恢复默认</button><text class="description">支持 JPG、PNG、WEBP，图片仅保存于当前设备。</text></view></view><view class="field"><text class="field-label">家族名称</text><input v-model="name" class="control" maxlength="20" placeholder="例如：江氏家族" /></view><text v-if="error" class="error-text">{{ error }}</text><view class="form-actions"><button class="btn" @click="backHome">取消</button><button class="btn primary" :disabled="busy" @click="save">保存资料</button></view></view></view>
</template>
<script setup>
import { ref } from 'vue'
import PageHeading from '../../components/PageHeading.vue'
import MemberAvatar from '../../components/MemberAvatar.vue'
import { store, useAuthGuard, saveProfile, backHome, notify } from '../../utils/store.js'
import { persistAvatar } from '../../utils/avatar.js'
useAuthGuard()
const name = ref(store.profile.name), avatar = ref(store.profile.avatar), error = ref(''), busy = ref(false)
function chooseAvatar() {
  uni.chooseImage({ count: 1, sizeType: ['compressed'], sourceType: ['album'], success: async result => {
    busy.value = true; error.value = ''
    try {
      if (result.tempFiles?.[0]?.size > 1024 * 1024) throw new Error('请选择小于 1 MB 的头像。')
      avatar.value = await persistAvatar(result.tempFilePaths[0])
    } catch (e) { error.value = e.message } finally { busy.value = false }
  }, fail: e => { if (!String(e.errMsg).includes('cancel')) error.value = '无法打开相册，请检查权限后重试。' } })
}
function save() { try { saveProfile({ name: name.value, avatar: avatar.value }); backHome(); notify('家族资料已保存') } catch (e) { error.value = e.message } }
</script>
<style scoped>.avatar-editor { display: flex; gap: 24px; align-items: center; margin: 8px 0 30px; }.avatar-editor .btn { max-width: 160px; }</style>
