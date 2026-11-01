// #ifdef H5
import {defineComponent,h} from 'vue'
export default defineComponent({setup:(p,{attrs,slots})=>()=>h('span',attrs,slots.default?.())})
// #endif
