// #ifdef H5
import {defineComponent,h,ref,onMounted,onUnmounted} from 'vue'
export default defineComponent({
  props:{demo:Boolean,contentWidth:Number},
  setup(props,{attrs,slots,expose}){
    const element=ref(null)
    function measure(){const e=element.value,root=e.getBoundingClientRect(),boxes={};if(!root.width)return null;e.querySelectorAll('.person-node').forEach(node=>{const r=node.getBoundingClientRect(),left=r.left-root.left+e.scrollLeft,top=r.top-root.top+e.scrollTop;boxes[node.dataset.personId || node.dataset.person]={left,top,right:left+r.width,bottom:top+r.height,width:r.width,height:r.height,centerX:left+r.width/2,centerY:top+r.height/2}});const padding=getComputedStyle(e);let width=Math.max(e.clientWidth,props.contentWidth||0),height=e.clientHeight;e.querySelectorAll('.generation-group').forEach(group=>{const r=group.getBoundingClientRect();width=Math.max(width,r.right-root.left+e.scrollLeft+(parseFloat(padding.paddingRight)||0));height=Math.max(height,r.bottom-root.top+e.scrollTop+(parseFloat(padding.paddingBottom)||0))});return {boxes,width,height}}
    function center(){const e=element.value,row=e?.querySelector('.tree-generation.first');if(!row)return;const root=e.getBoundingClientRect(),r=row.getBoundingClientRect();e.scrollLeft=Math.max(0,e.scrollLeft+r.left+r.width/2-root.left-root.width/2)}
    expose({measure,center})
    return ()=>h('section',{...attrs,ref:element},slots.default?.())
  }
})
// #endif
