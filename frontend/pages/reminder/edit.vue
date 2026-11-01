<template>
  <view class="page-wrap form-page" v-if="store.session">
    <PageHeading eyebrow="重要日子" :title="form.id ? '编辑提醒' : '新建提醒'" description="录入公历日期，自动换算农历。" />
    <view class="panel"><view class="form-grid">
      <view class="field"><text class="field-label">提醒名称 *</text><input v-model="form.title" class="control" maxlength="30" placeholder="例如：母亲生日" /></view>
      <view class="field"><text class="field-label">提醒类型</text><picker :range="types" :value="types.indexOf(form.type)" @change="form.type = types[$event.detail.value]"><view class="control">{{ form.type }} <text>⌄</text></view></picker></view>
      <view class="field full-field"><text class="field-label">相关人员（可选）</text><picker :range="choices" range-key="name" @change="form.memberId = choices[$event.detail.value].id"><view class="control">{{ memberName }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">公历日期 *</text><picker mode="date" :value="form.date || today" start="1000-01-01" end="2100-12-31" @change="form.date = $event.detail.value"><view class="control">{{ form.date || '请选择日期' }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">农历日期（自动换算）</text><view class="control readonly">{{ lunarDate(form.date) || '选择公历日期后显示' }}</view></view>
      <view class="field"><text class="field-label">提前提醒</text><picker :range="advances" :value="advances.indexOf(form.advance)" @change="form.advance = advances[$event.detail.value]"><view class="control">{{ form.advance }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">重复</text><picker :range="repeats" :value="repeats.indexOf(form.repeat)" @change="form.repeat = repeats[$event.detail.value]"><view class="control">{{ form.repeat }} <text>⌄</text></view></picker></view>
    </view><text class="description">每年重复按公历月日计算；2 月 29 日在下一个闰年出现。清明每年日期不同，祭扫安排默认只记录一次。</text><view class="notice">提醒显示在应用内日历，尚未接入系统通知或后台推送。</view><text v-if="error" class="error-text">{{ error }}</text><view class="form-actions reminder-actions"><button class="btn" @click="backHome">取消</button><button class="btn primary" @click="save">保存提醒</button></view></view>
  </view>
</template>
<script setup>
import { reactive, ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import PageHeading from '../../components/PageHeading.vue'
import { store, useAuthGuard, saveReminder, backHome, notify } from '../../utils/store.js'
import { dateString, lunarDate, parseDate } from '../../utils/dates.js'
useAuthGuard()
const today = dateString(), types = ['生日', '忌日', '传统祭日'], advances = ['当天', '提前 1 天', '提前 3 天', '提前 7 天', '提前 15 天'], repeats = ['每年', '仅一次']
const form = reactive({ id: '', title: '', type: '生日', memberId: '', date: '', advance: '提前 3 天', repeat: '每年' }), error = ref('')
const choices = computed(() => [{ id: '', name: '未关联' }, ...store.members])
const memberName = computed(() => choices.value.find(m => m.id === form.memberId)?.name || '未关联')
onLoad(q => {
  if (q.id) { const r = store.reminders.find(r => r.id === q.id); if (r) Object.assign(form, r); else { notify('提醒不存在'); backHome() } }
  if (q.date && parseDate(q.date)) form.date = q.date
  if (q.festival) Object.assign(form, { title: '清明祭扫', type: '传统祭日', repeat: '仅一次' })
  if (q.memberId) { const m = store.members.find(m => m.id === q.memberId); if (m) Object.assign(form, { memberId: m.id, title: m.name + (m.deceased ? '忌日' : '生日'), type: m.deceased ? '忌日' : '生日', date: m.deceased ? '' : m.birthday || '' }) }
})
function save() { try { saveReminder(form); backHome(); notify('提醒已保存') } catch (e) { error.value = e.message } }
</script>
<style scoped>.reminder-actions { margin-top: 24px; }</style>
