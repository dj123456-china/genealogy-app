<template><text :class="['ph', 'ph-' + name]" aria-hidden="true" /></template>
<script setup>defineProps({ name: { type: String, default: 'book-open-text' } })</script>
