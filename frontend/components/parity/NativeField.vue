<template>
  <picker v-if="kind === 'select'" :range="options" range-key="label" :value="selectedIndex" :disabled="disabled" @change="choose"><view class="native-select-value">{{ options[selectedIndex]?.label || options[0]?.label }}<text class="native-select-arrow">⌄</text></view></picker>
  <picker v-else-if="type === 'date'" mode="date" :value="modelValue || today" start="1000-01-01" end="2100-12-31" :disabled="disabled" @change="update($event.detail.value)"><view class="native-date-value">{{ modelValue || '年 / 月 / 日' }}<text class="ph ph-calendar-blank" /></view></picker>
  <checkbox-group v-else-if="type === 'checkbox'" @change="update($event.detail.value.length > 0)"><checkbox value="checked" :checked="!!modelValue" :disabled="disabled" color="#8b2f2a" /></checkbox-group>
  <textarea v-else-if="kind === 'textarea'" :value="modelValue" :placeholder="placeholder" :maxlength="maxlength || 500" :disabled="disabled || readonly" @input="update($event.detail.value)" />
  <view v-else-if="kind === 'datalist'" />
  <view v-else class="native-input-box"><input :type="type === 'number' || type === 'tel' ? 'number' : 'text'" :password="type === 'password'" :value="modelValue" :placeholder="placeholder" :maxlength="maxlength || 140" :disabled="disabled || readonly" @input="update($event.detail.value)" @focus="suggestionsOpen = true" @blur="closeSuggestions" @confirm="$emit('confirm')" /><view v-if="names?.length && suggestionsOpen" class="native-suggestions"><view v-for="name in matching" :key="name" @touchstart.stop="update(name); suggestionsOpen = false">{{ name }}</view></view></view>
</template>
<script setup>
import { computed, ref } from 'vue'
import { dateString } from '../../utils/dates.js'
const props = defineProps({ modelValue: [String, Number, Boolean], kind: { type:String, default:'input' }, type:String, options:Array, names:Array, placeholder:String, maxlength:[String,Number], disabled:Boolean, readonly:Boolean })
const emit = defineEmits(['update:modelValue','confirm','change'])
const today = dateString(), suggestionsOpen = ref(false)
const matching = computed(() => props.names.filter(n => n.includes(props.modelValue || '')).slice(0,8))
const selectedIndex = computed(() => Math.max(0, (props.options || []).findIndex(x => x.value === props.modelValue)))
function update(value) { emit('update:modelValue',value); emit('change',value) }
function choose(e) { update(props.options[+e.detail.value].value) }
function closeSuggestions() { setTimeout(() => { suggestionsOpen.value = false },180) }
</script>
