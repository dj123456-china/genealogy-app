<template>
  <view class="page-wrap form-page" v-if="store.session">
    <PageHeading eyebrow="家族档案" :title="form.id ? '编辑成员' : '录入家人'" description="完整记录姓名、世系与生平，让家族关系有据可查。" />
    <view class="panel"><view class="form-grid">
      <view class="field"><text class="field-label">中文姓名 *</text><input v-model="form.name" class="control" maxlength="12" placeholder="例如：江守诚" /></view>
      <view class="field"><text class="field-label">与我的关系 *</text><picker :range="RELATIONS" :value="RELATIONS.indexOf(form.relation)" @change="setRelation"><view class="control">{{ form.relation || '请选择关系' }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">性别</text><picker :range="genders" :value="genders.indexOf(form.gender)" @change="form.gender = genders[$event.detail.value]"><view class="control">{{ form.gender }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">世代</text><picker :range="generations" :value="form.generation - 1" @change="form.generation = +$event.detail.value + 1"><view class="control">第 {{ form.generation }} 代 <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">公历出生日期</text><picker mode="date" :value="form.birthday || today" start="1000-01-01" :end="today" @change="form.birthday = $event.detail.value"><view class="control">{{ form.birthday || '选择出生日期' }} <text>⌄</text></view></picker><button v-if="form.birthday" class="link" @click="form.birthday = ''">清空日期</button></view>
      <view class="field"><text class="field-label">农历日期（自动换算）</text><view class="control readonly">{{ lunarDate(form.birthday) || '选择公历日期后显示' }}</view></view>
      <view class="field"><text class="field-label">父母之一（可选）</text><picker :range="choices" range-key="name" @change="setParent('a', $event.detail.value)"><view class="control">{{ chosenName(parentA) }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">另一位父母（可选）</text><picker :range="choices" range-key="name" @change="setParent('b', $event.detail.value)"><view class="control">{{ chosenName(parentB) }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">配偶（可选）</text><picker :range="choices" range-key="name" @change="form.spouseId = choices[$event.detail.value].id"><view class="control">{{ chosenName(form.spouseId) }} <text>⌄</text></view></picker></view>
      <view class="field"><text class="field-label">头像显示文字</text><input v-model="form.avatarLabel" class="control" maxlength="2" placeholder="默认显示姓名末字" /></view>
      <view class="field"><text class="field-label">头像名称说明</text><input v-model="form.avatarName" class="control" maxlength="12" placeholder="例如：父亲、祖父" /></view>
      <view class="field full-field"><text class="field-label">生平简介</text><textarea v-model="form.bio" class="control" maxlength="2000" placeholder="记录籍贯、经历或想要留存的故事" /><text class="description">{{ form.bio.length }} / 2000</text></view>
    </view>
    <view class="check-row"><switch :checked="form.deceased" color="#8b2f2a" @change="form.deceased = $event.detail.value" /><text>该成员已故</text></view>
    <view v-if="form.deceased" class="field"><text class="field-label">卒年（公历，可选）</text><input v-model="form.deathYear" class="control" type="number" maxlength="4" placeholder="例如：2018" /></view>
    <text v-if="error" class="error-text">{{ error }}</text>
    <view class="form-actions"><button class="btn" @click="backHome">取消</button><button class="btn primary" @click="save">保存成员</button></view>
    </view>
  </view>
</template>
<script setup>
import { reactive, ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import PageHeading from '../../components/PageHeading.vue'
import { RELATIONS, generationFor, genderFor } from '../../utils/family.js'
import { dateString, lunarDate } from '../../utils/dates.js'
import { store, useAuthGuard, saveMember, notify, backHome } from '../../utils/store.js'
useAuthGuard()
const today = dateString(), genders = ['未知', '男', '女'], generations = Array.from({ length: 20 }, (_, i) => `第 ${i + 1} 代`)
const form = reactive({ id: '', name: '', relation: '', gender: '未知', generation: 3, birthday: '', deathYear: '', avatarLabel: '', avatarName: '', bio: '', deceased: false, spouseId: '' })
const parentA = ref(''), parentB = ref(''), error = ref('')
const choices = computed(() => [{ id: '', name: '未关联' }, ...store.members.filter(m => m.id !== form.id)])
const chosenName = id => choices.value.find(m => m.id === id)?.name || '未关联'
onLoad(query => { if (query.id) { const member = store.members.find(m => m.id === query.id); if (member) { Object.assign(form, member); parentA.value = member.parentIds?.[0] || ''; parentB.value = member.parentIds?.[1] || '' } else { notify('成员不存在'); backHome() } } })
function setRelation(event) {
  form.relation = RELATIONS[event.detail.value]
  form.generation = generationFor(form.relation, store.members, [parentA.value, parentB.value].filter(Boolean))
  const gender = genderFor(form.relation)
  if (gender !== '未知') form.gender = gender
}
function setParent(which, index) {
  const id = choices.value[index]?.id || ''
  if (which === 'a') parentA.value = id
  else parentB.value = id
  form.generation = generationFor(form.relation, store.members, [parentA.value, parentB.value].filter(Boolean))
}
function save() {
  try { saveMember({ ...form, parentIds: [parentA.value, parentB.value].filter(Boolean) }); backHome(); notify('成员已保存') }
  catch (e) { error.value = e.message }
}
</script>
