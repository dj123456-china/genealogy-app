<template>
  <scroll-view scroll-x scroll-y class="tree-scroll" :scroll-left="scrollLeft" :scroll-top="0" :scroll-with-animation="true">
    <view class="tree-canvas" :style="{ width: layout.width + 'px', height: layout.height + 'px' }">
      <view v-for="(segment, index) in segments" :key="'line-' + index" :class="['tree-line', segment.kind]" :style="{ left: segment.x + 'px', top: segment.y + 'px', width: segment.width + 'px', height: segment.height + 'px' }" />
      <text v-for="row in layout.rows" :key="'row-' + row.generation" class="generation-label" :style="{ top: row.y - 27 + 'px' }">第 {{ row.generation }} 代</text>
      <button v-for="node in layout.nodes" :key="node.member.id" class="person-node" :class="{ picked: selected.includes(node.member.id), faded: search && !matches(node.member), self: node.member.relation === '本人' }" :style="{ left: node.x + 'px', top: node.y + 'px' }" @click="$emit('select', node.member)">
        <MemberAvatar :name="node.member.name" :label="node.member.avatarLabel" /><text class="person-name">{{ node.member.name }}</text><text class="person-relation">{{ node.member.relation }}{{ node.member.deceased ? ' · 已故' : '' }}</text>
      </button>
    </view>
  </scroll-view>
</template>
<script setup>
import { computed, ref, nextTick, onMounted, onUnmounted } from 'vue'
import MemberAvatar from './MemberAvatar.vue'
import { familyEdges } from '../utils/family.js'
const props = defineProps({ members: { type: Array, default: () => [] }, selected: { type: Array, default: () => [] }, search: { type: String, default: '' } })
defineEmits(['select'])
const scrollLeft = ref(0)
const matches = m => `${m.name} ${m.relation}`.includes(props.search.trim())
const layout = computed(() => {
  const groups = [...new Set(props.members.map(m => m.generation || 3))].sort((a, b) => a - b).map(generation => ({ generation, members: props.members.filter(m => (m.generation || 3) === generation) }))
  const width = Math.max(660, ...groups.map(g => g.members.length * 176 + 90))
  const nodes = [], rows = []
  groups.forEach((group, index) => {
    const y = 55 + index * 195
    rows.push({ generation: group.generation, y })
    group.members.forEach((member, i) => nodes.push({ member, x: (width - group.members.length * 176) / 2 + i * 176 + 13, y }))
  })
  return { width, height: Math.max(300, groups.length * 195 + 36), nodes, rows }
})
const segments = computed(() => {
  const nodes = new Map(layout.value.nodes.map(n => [n.member.id, n])), parts = []
  const line = (x1, y1, x2, y2, kind) => parts.push({ x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.max(1, Math.abs(x2 - x1)), height: Math.max(1, Math.abs(y2 - y1)), kind })
  familyEdges(props.members).forEach(edge => {
    const a = nodes.get(edge.from), b = nodes.get(edge.to)
    if (edge.kind === 'spouse' && a.y === b.y) { const left = a.x < b.x ? a : b, right = left === a ? b : a; line(left.x + 150, left.y + 52, right.x, right.y + 52, 'spouse') }
    else {
      const x1 = a.x + 75, x2 = b.x + 75, y1 = a.y + 112, y2 = b.y, middle = (y1 + y2) / 2
      line(x1, y1, x1, middle, edge.kind); line(x1, middle, x2, middle, edge.kind); line(x2, middle, x2, y2, edge.kind)
    }
  })
  return parts
})
async function center() { scrollLeft.value = 0; await nextTick(); scrollLeft.value = Math.max(0, (layout.value.width - Math.min(1080, uni.getSystemInfoSync().windowWidth - 66)) / 2) }
onMounted(() => { center(); uni.onWindowResize(center) })
onUnmounted(() => { uni.offWindowResize(center) })
defineExpose({ center })
</script>
<style scoped>
.tree-scroll { width: 100%; height: 620px; background: #f6f3ed; border: 1px solid #cdc3ba; border-radius: 4px; }
.tree-canvas { position: relative; }
.generation-label { position: absolute; left: 22px; color: #88766b; font-size: 12px; letter-spacing: 2px; }
.person-node { line-height: 1.4; margin: 0; position: absolute; width: 150px; height: 112px; padding: 12px 8px; display: flex; align-items: center; flex-direction: column; background: #fffdf8; border: 1px solid #cdc3ba; border-radius: 4px; }
.person-node::after { border: 0; }
.person-node.self { border-color: #a05b48; background: #f0e4dc; }
.person-node.picked { border: 2px solid #8b2f2a; background: #ead9d5; }
.person-node.faded { opacity: .28; }
.person-name { font-size: 15px; margin-top: 5px; font-weight: 700; }
.person-relation { font-size: 11px; color: #6f645d; }
.tree-line { position: absolute; background: #a05b48; pointer-events: none; }
.tree-line.spouse { background: #8b2f2a; height: 2px !important; }
@media (max-width: 700px) { .tree-scroll { height: 590px; } }
</style>
