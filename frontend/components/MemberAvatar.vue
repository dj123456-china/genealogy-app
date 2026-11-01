<template><image v-if="src" :src="src" class="avatar" :class="{ large }" mode="aspectFill" /><view v-else class="avatar" :class="{ large }"><text>{{ label || name.slice(-1) || '谱' }}</text></view></template>
<script setup>defineProps({ name: { type: String, default: '' }, label: String, src: String, large: Boolean })</script>
