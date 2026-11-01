<template>
  <view class="panel relation-panel">
    <view class="relation-panel-heading"><view><text class="eyebrow">关系核验</text><text class="section-title">成员关系分析</text><text class="description">选择家谱成员核验关系，或按出生年份推测年龄差。</text></view><text aria-hidden="true" class="relation-panel-icon ph ph-git-branch" /></view>
    <view class="segments"><button :class="{ selected: mode === 'name' }" @click="changeMode('name')">按成员姓名</button><button :class="{ selected: mode === 'year' }" @click="changeMode('year')">按出生年份</button></view>
    <view v-if="mode === 'name'" class="query-fields">
      <view class="field"><text class="field-label">第一人</text><picker :range="members" range-key="name" @change="a = members[$event.detail.value].id"><view class="control relation-picker">{{ memberName(a) || '请选择成员' }} <text class="ph ph-caret-down" /></view></picker></view>
      <text aria-hidden="true" class="relation-query-link ph ph-arrows-left-right" />
      <view class="field"><text class="field-label">第二人</text><picker :range="members" range-key="name" @change="b = members[$event.detail.value].id"><view class="control relation-picker">{{ memberName(b) || '请选择成员' }} <text class="ph ph-caret-down" /></view></picker></view>
      <button class="btn primary" @click="analyze">分析关系</button>
    </view>
    <view v-else class="query-fields"><view class="field"><text class="field-label">第一人出生年份</text><input v-model="yearA" type="number" maxlength="4" placeholder="例如：1965" class="control" /></view><text aria-hidden="true" class="relation-query-link ph ph-arrows-left-right" /><view class="field"><text class="field-label">第二人出生年份</text><input v-model="yearB" type="number" maxlength="4" placeholder="例如：1992" class="control" /></view><button class="btn primary" @click="analyze">推测关系</button></view>
    <view class="relation-panel-hint">关系查询按具体成员档案核验，同名成员请按亲属称谓和世代选择；出生年份结果仅作年龄差推测。</view>
    <view class="notice relation-panel-result" :class="{ error: result && !result.ok }"><text class="ph ph-info" /><view><text>{{ result ? result.message : '选择两位成员后，可查看当前族谱中的关系路径。' }}</text><text v-if="result?.path" class="relation-path">{{ result.path }}</text><text v-if="result?.detail" class="description">{{ result.detail }}</text></view></view>
  </view>
</template>
<script setup>
import { ref } from 'vue'
import { analyzeRelationship, inferYears } from '../utils/family.js'
const props = defineProps({ members: { type: Array, default: () => [] } })
const mode = ref('name'), a = ref(''), b = ref(''), yearA = ref(''), yearB = ref(''), result = ref(null)
const memberName = id => props.members.find(m => m.id === id)?.name
function changeMode(value) { mode.value = value; result.value = null }
function analyze() { result.value = mode.value === 'name' ? analyzeRelationship(props.members, a.value, b.value) : inferYears(yearA.value, yearB.value) }
</script>
