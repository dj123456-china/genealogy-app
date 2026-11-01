<template><scroll-view scroll-x :scroll-left="scrollLeft" class="tree-scroll"><view class="family-tree tree-surface-content" :class="demo?'demo-family-tree':'user-family-tree'" :style="{minWidth:contentWidth+'px'}" :id="demo?'demoFamilyTree':'userFamilyTree'"><slot /></view></scroll-view></template>
<script>export default { inheritAttrs:false }</script>
<script setup>
import {ref,getCurrentInstance} from 'vue'
const props=defineProps({demo:Boolean,contentWidth:{type:Number,default:852}}),instance=getCurrentInstance(),scrollLeft=ref(0)
function measure(){return new Promise(resolve=>{uni.createSelectorQuery().in(instance).select('.family-tree').boundingClientRect().selectAll('.person-node').fields({rect:true,size:true,dataset:true}).exec(results=>{const root=results[0],boxes={};if(!root){resolve(null);return};for(const r of results[1]||[]){const left=r.left-root.left,top=r.top-root.top;boxes[r.dataset.personId || r.dataset.person]={left,top,right:left+r.width,bottom:top+r.height,width:r.width,height:r.height,centerX:left+r.width/2,centerY:top+r.height/2}}resolve({boxes,width:Math.max(props.contentWidth,root.width),height:root.height})})})}
function center(){scrollLeft.value=0;setTimeout(()=>{const width=uni.getSystemInfoSync().windowWidth;scrollLeft.value=Math.max(0,(props.contentWidth-(width-36))/2)},0)}
defineExpose({measure,center})
</script>
<style>
.tree-scroll { width:100%; }
.tree-surface-content { min-width:802px; }
</style>
