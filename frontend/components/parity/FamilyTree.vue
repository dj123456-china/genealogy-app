<template>
<TreeSurface ref="surface" class="family-tree" :class="demo?'demo-family-tree':'user-family-tree is-user-tree'" :id="demo?'demoFamilyTree':'userFamilyTree'" :demo="demo" :content-width="demo?852:layoutWidth+92" :aria-label="demo?'示范家族关系图':'我的家族关系图'">
<RelationshipLines :paths="paths" :width="width" :height="height" />
<view v-if="members.length" class="relationship-legend el-div" aria-label="关系线图例"><NativeText class="el-span"><NativeText class="legend-line spouse el-i" />配偶</NativeText><NativeText class="el-span"><NativeText class="legend-line parent el-i" />亲子</NativeText><NativeText v-if="demo" class="el-span"><NativeText class="legend-line sibling el-i" />同辈</NativeText></view>
<view v-if="!demo && !members.length" class="family-tree-empty el-div" id="familyTreeEmpty"><NativeText class="empty-tree-seal el-span">始</NativeText><view class="el-div"><NativeText class="eyebrow dark el-span">空白家谱</NativeText><view class="el-h3">从第一位家人开始</view><view class="el-p">录入家人，并选择父母或配偶建立世系连线。</view></view><NativeButton v-if="editable" class="btn btn-primary el-button" @click="$emit('add')"><NativeText class="ph ph-user-plus el-i" />添加第一位成员</NativeButton></view>
<view v-for="(row,i) in rows" :key="row.generation" class="generation-group" :style="demo?{}:{width:layoutWidth+'px'}" :class="{ 'demo-generation-group': demo, 'first-generation-group': i===0 }">
<view class="generation-label el-div" :class="demo?['','second-label','third-label'][i]:''">第{{row.generation}}代</view>
<view class="tree-generation el-div" :style="demo?{}:{width:layoutWidth+'px'}" :class="demo?['first','second','third'][i]:i===0?'first':'dynamic-generation'">
<view v-for="member in row.members" :key="member.id" class="person-node el-div" :class="{'demo-person-node':demo,current:member.relation==='本人','search-hidden':hidden(member),'relation-selected':selected?.includes(member.id)}" :data-person="member.name" :data-person-id="member.id" :role="demo?undefined:'button'" :tabindex="demo?undefined:0" @click="!demo && $emit('person',member)" @keydown.enter="!demo && $emit('person',member)"><NativeText class="avatar avatar-text el-span">{{member.avatarLabel || (demo && member.name==='江建国'?'建':member.name.slice(-1))}}</NativeText><NativeText class="el-span"><NativeText class="el-strong">{{member.name}}</NativeText><NativeText class="el-small">{{member.avatarName || member.relation}}{{demo && i===0?' · 资料待补充':''}}</NativeText></NativeText></view>
</view>
</view>
</TreeSurface>
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
import {computed,ref,nextTick,onMounted,watch,onUnmounted} from 'vue'
import {displayGeneration,demoEdges} from '../../utils/parity-domain.js'
import {familyEdges} from '../../utils/family.js'
import {relationshipPaths} from '../../utils/tree-paths.js'
// #ifdef H5
import TreeSurface from './TreeSurface.h5.js'
import RelationshipLines from './RelationshipLines.h5.js'
// #endif
// #ifndef H5
import TreeSurface from './TreeSurface.vue'
import RelationshipLines from './RelationshipLines.vue'
// #endif
const props=defineProps({members:{type:Array,default:()=>[]},search:String,selected:Array,demo:Boolean,editable:{type:Boolean,default:true}})
defineEmits(['person','add'])
const surface=ref(null),paths=ref([]),width=ref(852),height=ref(720)
const rows=computed(()=>[...new Set(props.members.map(displayGeneration))].sort((a,b)=>a-b).map(g=>({generation:g,members:props.members.filter(m=>displayGeneration(m)===g)})))
const layoutWidth=computed(()=>Math.max(760,...rows.value.map(row=>row.members.length*180+Math.max(0,row.members.length-1)*28)))
const hidden=m=>!!props.search?.trim()&&!`${m.name}${m.relation}${m.avatarName||''}`.toLowerCase().includes(props.search.trim().toLowerCase())
let frame
async function center(){await nextTick();surface.value?.center();const result=await surface.value?.measure();if(result){width.value=result.width;height.value=result.height;paths.value=relationshipPaths(result.boxes,props.members,props.demo?demoEdges:familyEdges(props.members));width.value=Math.max(width.value,...paths.value.map(p=>p.x+42))}}
function schedule(){clearTimeout(frame);frame=setTimeout(center,60)}
onMounted(schedule);onUnmounted(()=>clearTimeout(frame));watch(()=>props.members,schedule,{deep:true});defineExpose({center})
</script>
