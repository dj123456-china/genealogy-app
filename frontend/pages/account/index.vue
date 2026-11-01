<template>
  <view class="page-wrap" v-if="store.session">
    <PageHeading eyebrow="本机典藏" title="我的家谱" />
    <view class="panel account-hero"><MemberAvatar :name="store.profile.name" :src="store.profile.avatar" :label="store.profile.name.slice(0, 1)" large /><view class="account-copy"><text class="page-title">{{ store.profile.name }}</text><text class="description">本机资料 · {{ store.session.username }} 已登录</text></view><button class="btn" @click="editProfile">自定义头像与名称</button></view>
    <view class="account-grid"><view class="panel archive"><AppIcon name="book-open-text" /><text class="eyebrow">本机资料</text><text class="section-title">家谱档案</text><text class="description">{{ store.members.length }} 位成员 · {{ store.reminders.length }} 条纪念日</text><text class="description">成员、关系、纪念日和家族资料均保存在当前设备的本机账号下。</text></view><view class="panel"><text class="section-title">账户与隐私</text><button class="setting" @click="privacy"><AppIcon name="shield-check" /><text>隐私与授权</text><AppIcon name="caret-right" /></button><button class="setting" @click="signOut"><AppIcon name="sign-out" /><text>退出登录</text><AppIcon name="caret-right" /></button><button class="setting danger" @click="clearData"><AppIcon name="trash" /><text>清空当前账号家谱</text><AppIcon name="caret-right" /></button></view></view>
    <text class="description">家谱制作器 2.0 · 资料保存在本机，卸载应用或清除存储会丢失资料。</text>
  </view>
</template>
<script setup>
import PageHeading from '../../components/PageHeading.vue'
import MemberAvatar from '../../components/MemberAvatar.vue'
import AppIcon from '../../components/AppIcon.vue'
import { store, useAuthGuard, logout, clearCurrentData, notify } from '../../utils/store.js'
useAuthGuard()
function editProfile() { uni.navigateTo({ url: '/pages/profile/index' }) }
function privacy() { uni.showModal({ title: '隐私与授权', content: '本应用未接入服务器，不上传家谱或密码。密码使用加盐 PBKDF2 校验；本机资料未加密。头像仅在你主动选择时访问相册。应用内日历不发送系统通知。', showCancel: false, confirmColor: '#8b2f2a' }) }
function signOut() { uni.showModal({ title: '退出登录', content: '家谱会保留在当前设备，下次登录同一账号可继续查看。', confirmColor: '#8b2f2a', success: r => { if (r.confirm) { try { logout() } catch { notify('退出失败，请重试') } } } }) }
function clearData() { uni.showModal({ title: '清空当前账号家谱', content: '将永久删除当前账号的成员、关系、纪念日和自定义资料。账号仍保留，其他账号不受影响。确认清空？', confirmText: '确认清空', confirmColor: '#8b2f2a', success: r => { if (r.confirm) { try { clearCurrentData(); notify('当前账号家谱已清空') } catch (e) { notify(e.message) } } } }) }
</script>
<style scoped>
.account-hero { display: flex; gap: 22px; align-items: center; padding: 30px; }
.account-copy { flex: 1; }
.account-grid { display: grid; grid-template-columns: 1fr 1.3fr; gap: 22px; }
.archive { background: #e6ded1; }
.archive > .ph { display: block; color: #8b2f2a; font-size: 32px; margin-bottom: 20px; }
.setting { line-height: 1.5; display: flex; align-items: center; gap: 14px; width: 100%; padding: 19px 0; border-bottom: 1px solid #cdc3ba; text-align: left; font-size: 14px; }
.setting text:nth-child(2) { flex: 1; }.setting .ph { font-size: 21px; }.setting.danger { color: #8b2f2a; }
@media (max-width: 700px) { .account-hero { flex-wrap: wrap; padding: 22px; gap: 16px; } .account-hero .btn { width: 100%; } .account-hero .page-title { font-size: 22px; } .account-grid { grid-template-columns: 1fr; gap: 0; } }
</style>
