// #ifdef H5
import {defineComponent,h,onMounted,onUnmounted,ref} from 'vue'
export default defineComponent({
  setup(p,{attrs,slots}) {
    const form=ref(null)
    function validate(event){const target=event.target.closest('button');if(target && /^(saveMember|saveReminder|saveProfile|submitLogin)$/.test(target.id) && !form.value.reportValidity()){event.preventDefault();event.stopImmediatePropagation()}}
    onMounted(()=>form.value.addEventListener('click',validate,true));onUnmounted(()=>form.value?.removeEventListener('click',validate,true))
    return ()=>h('form',{...attrs,ref:form,onSubmit:event=>event.preventDefault()},slots.default?.())
  }
})
// #endif
