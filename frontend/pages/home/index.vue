<template>
  <view class="page-wrap" v-if="store.session">
    <PageHeading :eyebrow="todayLabel" title="家族首页"><button class="btn primary" @click="openMember()"><AppIcon name="user-plus" />录入家人</button></PageHeading>
    <view class="hero"><image src="/static/images/family-cover.jpg" class="hero-image" mode="aspectFill" /><view class="hero-shade" /><view class="hero-copy"><text class="hero-eyebrow">{{ store.profile.name }} · 宗谱数字典藏</text><view class="hero-title"><text>修谱存史</text><text>敬宗睦族</text></view><text class="hero-description">谨录世系、生平与纪念日，保存完整可靠的家族档案。</text><view class="actions"><button class="btn paper" @click="toTab('genealogy')">查看家族谱</button><button class="btn hero-secondary" @click="openMember()">添加成员</button></view></view><view class="hero-seal"><text>{{ store.profile.name.slice(0, 2) }}</text><text>家谱</text></view></view>
    <view class="stats"><view class="stat"><AppIcon name="users-three" /><view><text class="stat-number">{{ store.members.length }}</text><text class="description">已录入成员</text></view></view><view class="stat"><AppIcon name="git-branch" /><view><text class="stat-number">{{ generations }}</text><text class="description">已整理世代</text></view></view></view>
    <view class="home-grid"><view class="panel"><view class="section-heading"><view><text class="section-title">近期重要日子</text><text class="description">生日、忌日和传统祭日集中记录</text></view><button class="link" @click="toTab('reminders')">查看全部 →</button></view>
      <button v-for="event in upcoming" :key="event.id" class="event-row" @click="toTab('reminders')"><view class="event-date"><text class="event-day">{{ event.next.slice(8) }}</text><text class="event-month">{{ +event.next.slice(5, 7) }} 月</text></view><AppIcon :name="event.type === '生日' ? 'cake' : 'calendar-dots'" /><view class="event-copy"><text class="event-name">{{ event.title }}</text><text class="description">{{ lunarDate(event.next) }}</text></view><text class="event-count">{{ countdown(event.next) }}</text></button>
      <view v-if="!upcoming.length" class="empty"><text>还没有近期纪念日</text><button class="btn" @click="newReminder">记录第一个重要日子</button></view>
    </view><view class="panel festival"><text class="eyebrow">下一次清明祭扫</text><text class="festival-title">清明</text><text>{{ qingming }}</text><text class="description">核验祭扫日期与地点，把家族的约定记入日历。</text><button class="btn primary full" @click="newQingming">记录祭扫安排</button></view></view>
    <RelationAnalyzer :members="store.members" />
  </view>
</template>
<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import PageHeading from '../../components/PageHeading.vue'
import AppIcon from '../../components/AppIcon.vue'
import RelationAnalyzer from '../../components/RelationAnalyzer.vue'
import { store, useAuthGuard, openMember } from '../../utils/store.js'
import { dateString, nextOccurrence, countdown, lunarDate, qingmingDate, dayDistance } from '../../utils/dates.js'
useAuthGuard()
const today = ref(dateString())
onShow(() => { today.value = dateString() })
const todayLabel = computed(() => `${today.value.replaceAll('-', ' / ')} · ${lunarDate(today.value)}`)
const generations = computed(() => new Set(store.members.map(m => m.generation)).size)
const upcoming = computed(() => store.reminders.map(r => ({ ...r, next: nextOccurrence(r, new Date(today.value + 'T12:00:00')) })).filter(r => dayDistance(r.next, new Date(today.value + 'T12:00:00')) >= 0).sort((a, b) => a.next.localeCompare(b.next)).slice(0, 3))
const qingming = computed(() => { const y = +today.value.slice(0, 4); const q = qingmingDate(y); return q < today.value ? qingmingDate(y + 1) : q })
function toTab(name) { uni.switchTab({ url: `/pages/${name}/index` }) }
function newReminder() { uni.navigateTo({ url: '/pages/reminder/edit' }) }
function newQingming() { uni.navigateTo({ url: `/pages/reminder/edit?date=${qingming.value}&festival=1` }) }
</script>
<style scoped>
.hero { height: 360px; position: relative; overflow: hidden; border-radius: 4px; color: #fffaf3; }
.hero-image, .hero-shade { position: absolute; width: 100%; height: 100%; }
.hero-shade { background: linear-gradient(90deg, rgba(31, 25, 19, .87), rgba(31, 25, 19, .08)); }
.hero-copy { position: relative; padding: 34px 40px; max-width: 600px; }
.hero-eyebrow { font-size: 12px; letter-spacing: 3px; }
.hero-title { display: block; white-space: pre-line; font-size: 46px; letter-spacing: 6px; line-height: 1.35; margin: 14px 0; font-weight: 700; }
.hero-title text { display: block; }
.hero-description { display: block; font-size: 14px; opacity: .85; margin-bottom: 24px; }
.hero-secondary { background: transparent; color: #fffaf3; border-color: #c9bfb2; }
.hero-seal { position: absolute; right: 28px; bottom: 30px; display: flex; flex-direction: column; border: 2px solid #e6ded1; padding: 8px; font-size: 22px; line-height: 1.4; }
.stats { display: flex; margin: 22px 0; border: 1px solid #cdc3ba; background: #f6f3ed; }
.stat { width: 50%; display: flex; align-items: center; justify-content: center; gap: 20px; padding: 20px; }
.stat + .stat { border-left: 1px solid #cdc3ba; }
.stat .ph { font-size: 28px; color: #8b2f2a; }
.stat-number { font-size: 30px; font-weight: 700; line-height: 1; }
.home-grid { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 22px; }
.festival { background: #e6ded1; }
.festival-title { display: block; font-size: 40px; letter-spacing: 6px; margin: 14px 0; }
.festival .btn { margin-top: 24px; }
@media (max-width: 700px) { .hero { height: 330px; } .hero-copy { padding: 26px 22px; } .hero-title { font-size: 37px; } .hero-title text { display: block; }
.hero-description { max-width: 240px; } .hero-seal { display: none; } .hero .btn { padding: 9px 12px; } .home-grid { grid-template-columns: 1fr; gap: 0; } .stat { gap: 12px; padding: 15px; } .stat-number { font-size: 27px; } }
</style>
