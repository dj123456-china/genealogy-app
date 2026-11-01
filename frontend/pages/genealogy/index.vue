<template>
  <view class="page-wrap" v-if="store.session">
    <PageHeading eyebrow="家族脉络" :title="store.profile.name + '谱'" description="只记录你录入的家人，示范族谱可单独查看。"><button class="btn primary" @click="openMember()"><AppIcon name="plus" />添加成员</button></PageHeading>
    <view class="toolbar"><input v-model="search" class="control search" placeholder="搜索姓名或关系" /><view class="segments"><button v-for="item in views" :key="item.value" :class="{ selected: view === item.value }" @click="changeView(item.value)">{{ item.label }}</button></view><button class="icon-btn" aria-label="居中族谱" @click="tree?.center()"><AppIcon name="crosshair" /></button></view>
    <view class="selection-bar"><text>{{ selecting ? (selected.length ? '已选 1 人，请选择第二位成员' : '请依次点击两位成员') : '点击成员查看档案，选择两人可分析关系。' }}</text><button class="link" @click="toggleSelection">{{ selecting ? '取消选择' : '选择两人' }}</button></view>
    <view v-if="view === 'demo'" class="notice demo-notice"><text>示范族谱 · 仅用于展示，不会写入你的家谱。</text><button class="link" @click="changeView('tree'); openMember()">开始录入我的家谱 →</button></view>
    <view v-if="!members.length" class="panel empty"><text class="empty-seal">始</text><text class="section-title">从第一位家人开始</text><text>这里会保存你亲自录入的家人。</text><button class="btn primary" @click="openMember()">添加第一位成员</button></view>
    <view v-else-if="view === 'directory'" class="directory"><button v-for="member in filtered" :key="member.id" class="directory-card" :class="{ picked: selected.includes(member.id) }" @click="selectMember(member)"><MemberAvatar :name="member.name" :label="member.avatarLabel" /><view class="directory-copy"><text class="section-title">{{ member.name }}</text><text class="description">{{ member.relation }} · 第 {{ member.generation }} 代</text></view><AppIcon name="caret-right" /></button><view v-if="!filtered.length" class="empty">未找到匹配成员，请换个关键词。</view></view>
    <FamilyTree v-else ref="tree" :members="members" :selected="selected" :search="search" @select="selectMember" />
    <text v-if="members.length && view !== 'directory'" class="description">横向、纵向滑动查看完整族谱。连线依据已填写的父母和配偶；深红线为婚姻，棕色线为亲子。</text>
    <view v-if="result" class="panel result-panel"><view class="section-heading"><text class="section-title">两人关系结果</text><button class="link" @click="result = null">关闭</button></view><view class="notice" :class="{ error: !result.ok }"><text>{{ result.message }}</text><text v-if="result.path" class="relation-path">{{ result.path }}</text><text v-if="result.detail" class="description">{{ result.detail }}</text></view><button class="link" @click="selected = []; selecting = true; result = null">重新选择两人 →</button></view>
  </view>
</template>
<script setup>
import { ref, computed } from 'vue'
import PageHeading from '../../components/PageHeading.vue'
import AppIcon from '../../components/AppIcon.vue'
import MemberAvatar from '../../components/MemberAvatar.vue'
import FamilyTree from '../../components/FamilyTree.vue'
import { store, useAuthGuard, openMember } from '../../utils/store.js'
import { DEMO_MEMBERS, analyzeRelationship } from '../../utils/family.js'
useAuthGuard()
const view = ref('tree'), search = ref(''), tree = ref(null), selecting = ref(false), selected = ref([]), result = ref(null)
const views = [{ value: 'tree', label: '家族树' }, { value: 'directory', label: '成员名录' }, { value: 'demo', label: '示范' }]
const members = computed(() => view.value === 'demo' ? DEMO_MEMBERS : store.members)
const filtered = computed(() => members.value.filter(m => `${m.name} ${m.relation}`.includes(search.value.trim())))
function changeView(value) { view.value = value; selected.value = []; selecting.value = false; result.value = null; search.value = '' }
function toggleSelection() { selecting.value = !selecting.value; selected.value = []; result.value = null }
function selectMember(member) {
  if (!selecting.value) { uni.navigateTo({ url: `/pages/member/detail?id=${member.id}${view.value === 'demo' ? '&demo=1' : ''}` }); return }
  if (selected.value.includes(member.id)) { selected.value = selected.value.filter(id => id !== member.id); return }
  selected.value.push(member.id)
  if (selected.value.length === 2) { result.value = analyzeRelationship(members.value, ...selected.value); selecting.value = false; uni.showModal({ title: '两人关系结果', content: result.value.message + (result.value.path ? '\n' + result.value.path : ''), showCancel: false, confirmColor: '#8b2f2a' }) }
}
</script>
<style scoped>
.toolbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.search { flex: 1; min-width: 180px; }
.toolbar .segments { margin: 0; }
.selection-bar { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: #6f645d; margin: 12px 0; gap: 12px; }
.selection-bar .link { flex-shrink: 0; }
.demo-notice { margin: 0 0 18px; }
.directory { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.directory-card { line-height: 1.5; background: #f6f3ed; border: 1px solid #cdc3ba; display: flex; align-items: center; gap: 14px; padding: 20px; text-align: left; }
.directory-card.picked { background: #ead9d5; border-color: #8b2f2a; }
.directory-copy { flex: 1; }
.result-panel { margin-top: 20px; }
@media (max-width: 700px) { .search { flex-basis: 100%; } .toolbar .segments { flex: 1; } .segments button { padding: 8px 9px; } .directory { grid-template-columns: 1fr; } }
</style>
