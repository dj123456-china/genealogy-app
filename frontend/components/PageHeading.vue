<template>
  <view class="page-heading">
    <view><text class="eyebrow">{{ eyebrow }}</text><text class="page-title">{{ title }}</text><text v-if="description" class="description">{{ description }}</text></view>
    <view class="heading-action"><slot /></view>
  </view>
</template>
<script setup>defineProps({ title: String, eyebrow: String, description: String })</script>
