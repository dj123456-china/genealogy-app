<template>
  <view class="page-wrap" v-if="store.session">
    <PageHeading eyebrow="家族日历" title="重要日子，集中记录" description="记录生日、忌日和传统祭日，点击日历日期添加提醒。"><button class="btn primary" @click="edit()"><AppIcon name="calendar-plus" />新建提醒</button></PageHeading>
    <view class="calendar-layout"><view class="panel calendar"><view class="calendar-heading"><button class="icon-btn" aria-label="上个月" @click="changeMonth(-1)"><AppIcon name="caret-left" /></button><view><text class="section-title">{{ year }} 年 {{ month + 1 }} 月</text><text class="description">{{ lunarDate(monthFirst) }}</text></view><button class="icon-btn" aria-label="下个月" @click="changeMonth(1)"><AppIcon name="caret-right" /></button></view><view class="week-grid"><text v-for="day in weekdays" :key="day">{{ day }}</text></view><view class="date-grid"><view v-for="cell in cells" :key="cell.key" class="date-cell"><button v-if="cell.date" class="day-button" :class="{ today: cell.date === today, selected: cell.date === selectedDate }" @click="selectedDate = cell.date"><text>{{ cell.day }}</text><text class="lunar-day">{{ cell.lunar }}</text><view class="day-marks"><view v-for="type in cell.types" :key="type" :class="['day-mark', type === '生日' ? 'birthday' : type === '忌日' ? 'memorial' : 'festival']" /></view></button></view></view><view class="legend"><text>● 生日</text><text>● 忌日</text><text>● 传统祭日</text></view><view class="selected-date"><text>{{ selectedDate }} · {{ lunarDate(selectedDate) }}</text><button class="link" @click="edit('', selectedDate)">这天添加提醒 +</button></view><view v-if="selectedReminders.length"><view v-for="r in selectedReminders" :key="r.id" class="selected-reminder" @click="edit(r.id)">{{ r.title }} · {{ r.type }} →</view></view><text v-else class="description">这一天还没有提醒记录。</text></view>
      <view class="panel upcoming"><view class="section-heading"><view><text class="section-title">接下来的提醒</text><text class="description">保存在当前账号 · 应用内提醒</text></view></view><view v-if="!events.length" class="empty"><AppIcon name="calendar-dots" /><text class="description">还没有提醒记录</text></view><view v-for="event in events" :key="event.id" class="timeline-event"><view class="event-header"><text class="tag">{{ event.type }}</text><text class="event-count">{{ countdown(event.next) }}</text></view><button class="event-detail" @click="edit(event.id)"><text class="event-name">{{ event.title }}</text><text class="description">{{ event.next }} · {{ lunarDate(event.next) }}</text><text v-if="nameOf(event.memberId)" class="description">{{ nameOf(event.memberId) }}</text></button><view class="event-footer"><text class="tag">{{ event.advance }} · {{ event.repeat }}</text><button class="link" @click="remove(event)">删除</button></view></view></view>
    </view>
  </view>
</template>
<script setup>
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import PageHeading from '../../components/PageHeading.vue'
import AppIcon from '../../components/AppIcon.vue'
import { store, useAuthGuard, deleteReminder, notify } from '../../utils/store.js'
import { dateString, lunarDate, nextOccurrence, countdown, remindersForDate, dayDistance } from '../../utils/dates.js'
useAuthGuard()
const now = new Date(), today = ref(dateString()), year = ref(now.getFullYear()), month = ref(now.getMonth()), selectedDate = ref(dateString()), weekdays = ['一', '二', '三', '四', '五', '六', '日']
onShow(() => { today.value = dateString() })
const monthFirst = computed(() => dateString(new Date(year.value, month.value, 1)))
const cells = computed(() => {
  const offset = (new Date(year.value, month.value, 1).getDay() + 6) % 7, total = new Date(year.value, month.value + 1, 0).getDate()
  return Array.from({ length: Math.ceil((offset + total) / 7) * 7 }, (_, i) => {
    const day = i - offset + 1
    if (day < 1 || day > total) return { key: i }
    const date = dateString(new Date(year.value, month.value, day)), lunar = lunarDate(date)
    return { key: i, day, date, lunar: lunar.split('月').pop(), types: [...new Set(remindersForDate(store.reminders, date).map(r => r.type))] }
  })
})
const selectedReminders = computed(() => remindersForDate(store.reminders, selectedDate.value))
const events = computed(() => {
  const now = new Date(today.value + 'T12:00:00')
  return store.reminders.map(r => ({ ...r, next: nextOccurrence(r, now) })).sort((a, b) => { const ap = dayDistance(a.next, now) < 0, bp = dayDistance(b.next, now) < 0; return ap !== bp ? (ap ? 1 : -1) : a.next.localeCompare(b.next) })
})
const nameOf = id => store.members.find(m => m.id === id)?.name
function changeMonth(delta) { const date = new Date(year.value, month.value + delta, 1); year.value = date.getFullYear(); month.value = date.getMonth(); selectedDate.value = dateString(date) }
function edit(id = '', date = '') { uni.navigateTo({ url: '/pages/reminder/edit' + (id ? `?id=${id}` : date ? `?date=${date}` : '') }) }
function remove(event) { uni.showModal({ title: '删除提醒', content: `确定删除“${event.title}”？`, confirmColor: '#8b2f2a', success: r => { if (r.confirm) { try { deleteReminder(event.id); notify('提醒已删除') } catch (e) { notify(e.message) } } } }) }
</script>
<style scoped>
.calendar-layout { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(300px, 1fr); gap: 24px; align-items: start; }
.calendar-heading { display: flex; align-items: center; justify-content: space-between; text-align: center; margin-bottom: 24px; }
.week-grid, .date-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); }
.week-grid { text-align: center; color: #6f645d; font-size: 13px; padding-bottom: 12px; }
.date-cell { min-height: 72px; }
.day-button { line-height: 1.4; height: 68px; padding: 7px 0; display: flex; align-items: center; flex-direction: column; margin: 2px; border: 1px solid transparent; }
.day-button.today { color: #8b2f2a; font-weight: 700; }
.day-button.selected { border-color: #8b2f2a; background: #ead9d5; }
.lunar-day { font-size: 10px; color: #8b7b6e; }
.day-marks { display: flex; gap: 3px; height: 5px; margin-top: 3px; }
.day-mark { width: 4px; height: 4px; border-radius: 50%; background: #8b2f2a; }
.day-mark.memorial { background: #7a655d; }.day-mark.festival { background: #8d735e; }
.legend { display: flex; gap: 16px; font-size: 11px; color: #8b2f2a; border-top: 1px solid #cdc3ba; padding-top: 16px; }
.legend text:nth-child(2) { color: #7a655d; }.legend text:nth-child(3) { color: #8d735e; }
.selected-date { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; margin-top: 20px; font-size: 12px; }
.selected-reminder { margin-top: 8px; padding: 8px 12px; background: #eae2d9; font-size: 13px; }
.timeline-event { border-top: 1px solid #cdc3ba; padding: 18px 0 6px; }
.event-header, .event-footer { display: flex; justify-content: space-between; align-items: center; }
.event-detail { line-height: 1.5; text-align: left; padding: 10px 0; }
@media (max-width: 800px) { .calendar-layout { grid-template-columns: 1fr; gap: 0; } .calendar { padding: 16px 10px; } .day-button { margin: 1px; } .date-cell { min-height: 62px; } .day-button { line-height: 1.4; height: 60px; } .calendar-heading { margin-bottom: 16px; } }
</style>
