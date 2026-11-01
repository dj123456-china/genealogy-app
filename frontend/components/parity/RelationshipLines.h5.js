// #ifdef H5
import {defineComponent,h} from 'vue'
export default defineComponent({props:{paths:Array,width:Number,height:Number},setup:p=>()=>h('svg',{class:'relationship-lines',width:p.width,height:p.height,viewBox:`0 0 ${p.width} ${p.height}`,'aria-hidden':true},(p.paths||[]).flatMap(line=>[
  h('path',{class:'relationship-path-halo',d:line.d}),h('path',{class:`relationship-path is-${line.kind}`,d:line.d},[h('title',line.description)]),
  h('g',{class:'relationship-line-label'},[h('rect',{class:`relationship-label-box is-${line.kind}`,x:line.x-22,y:line.y-10,width:44,height:20,rx:10}),h('text',{class:`relationship-label-text is-${line.kind}`,x:line.x,y:line.y},line.label)])
]))})
// #endif
