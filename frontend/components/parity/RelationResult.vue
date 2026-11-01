<template>
<view class="relation-result el-div" :class="{'relation-dialog-result':dialog,'is-estimate':result?.estimated,'is-error':result && !result.ok}" aria-live="polite">
  <NativeText class="ph el-i" :class="!result?'ph-info':!result.ok?'ph-warning-circle':result.estimated?'ph-sparkle':'ph-git-branch'" />
  <NativeText class="el-span" v-if="!result">选择两位成员后，可查看当前族谱中的关系路径。</NativeText>
  <NativeText class="el-span" v-else-if="!result.ok">{{result.message || '暂时无法分析。'}}</NativeText>
  <NativeText class="el-span" v-else><NativeText class="relation-headline el-strong">{{result.headline}}</NativeText><NativeText class="relation-confidence el-span">{{result.detail}}</NativeText><NativeText v-if="result.path" class="relation-path el-span">路径：{{result.path}}</NativeText></NativeText>
</view>
</template>
<script setup>
// #ifdef H5
import NativeText from './NativeText.h5.js'
import NativeButton from './NativeButton.h5.js'
// #endif
// #ifndef H5
import NativeText from './NativeText.vue'
import NativeButton from './NativeButton.vue'
// #endif

defineProps({result:Object,dialog:Boolean})
</script>
