<template><image :src="src" :alt="alt" mode="aspectFill" /></template>
<script setup>
defineProps({src:String,alt:String})
</script>
