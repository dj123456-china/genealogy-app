<template>
  <view v-if="member && store.session" class="page-wrap form-page">
    <PageHeading :eyebrow="demo ? '示范成员 · 不计入你的家谱' : '成员档案'" :title="member.name" />
    <view class="panel"><view class="person-summary"><MemberAvatar :name="member.name" :label="member.avatarLabel" large /><view><text class="section-title">{{ member.relation }}</text><text class="description">第 {{ member.generation }} 代 · {{ member.gender || '性别未记录' }}</text><text v-if="member.avatarName" class="description">{{ member.avatarName }}</text></view></view>
      <view class="record"><text class="field-label">生卒信息</text><text>{{ member.birthday || '出生日期待补充' }}{{ member.deceased ? ' — ' + (member.deathYear || '卒年待补充') : '' }}</text><text class="description">{{ lunarDate(member.birthday) }}</text></view>
      <view class="record"><text class="field-label">家庭关联</text><text>父母：{{ parents || '尚未关联' }}</text><text class="description">配偶：{{ spouse || '尚未关联' }}</text></view>
      <view class="record"><text class="field-label">生平事迹</text><text class="biography">{{ member.bio || '尚未记录生平事迹。' }}</text></view>
      <view v-if="!demo" class="actions"><button class="btn" @click="openMember(member.id)">编辑资料</button><button class="btn primary" @click="setReminder">设置提醒</button><button class="btn danger" @click="remove">删除成员</button></view>
      <view v-else class="notice">示范资料仅用于展示排版与关系，不会写入你的家谱。</view>
    </view>
  </view>
</template>
<script setup>
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import PageHeading from '../../components/PageHeading.vue'
import MemberAvatar from '../../components/MemberAvatar.vue'
import { store, useAuthGuard, openMember, deleteMember, notify, backHome } from '../../utils/store.js'
import { DEMO_MEMBERS } from '../../utils/family.js'
import { lunarDate } from '../../utils/dates.js'
useAuthGuard()
const id = ref(''), demo = ref(false)
onLoad(q => { id.value = q.id; demo.value = q.demo === '1'; if (!member.value) { notify('成员不存在'); backHome() } })
const list = computed(() => demo.value ? DEMO_MEMBERS : store.members)
const member = computed(() => list.value.find(m => m.id === id.value))
const parents = computed(() => (member.value?.parentIds || []).map(id => list.value.find(m => m.id === id)?.name).filter(Boolean).join('、'))
const spouse = computed(() => list.value.find(m => m.id === member.value?.spouseId)?.name)
function setReminder() { uni.navigateTo({ url: `/pages/reminder/edit?memberId=${id.value}` }) }
function remove() { uni.showModal({ title: '删除成员', content: '删除后会解除该成员的家庭关联，已有纪念日会保留。确认删除？', confirmColor: '#8b2f2a', success: result => { if (result.confirm) { try { deleteMember(id.value); backHome(); notify('成员已删除') } catch (e) { notify(e.message) } } } }) }
</script>
<style scoped>
.person-summary { display: flex; gap: 20px; align-items: center; margin-bottom: 26px; }
.record { border-top: 1px solid #cdc3ba; padding: 22px 0; }
.biography { white-space: pre-wrap; }
</style>
