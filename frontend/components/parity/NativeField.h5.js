// #ifdef H5
// Web 使用 Vue 渲染原生表单控件，保留原项目输入框、日期、下拉框的样式和键盘行为。
import { defineComponent, h, ref, onMounted } from 'vue'
export default defineComponent({
  inheritAttrs: false,
  props: { modelValue: [String, Number, Boolean], kind: { default: 'input' }, options: Array, names: Array },
  emits: ['update:modelValue', 'confirm', 'change'],
  setup(props, { attrs, emit }) {
    const field = ref(null)
    onMounted(() => { if(['loginIdentifier', 'loginUsername', 'loginPhone'].includes(attrs.id)) field.value?.focus({ preventScroll: true }) })
    return () => {
      if (props.kind === 'datalist') return h('datalist', attrs, (props.names || []).map(name => h('option', { value: name })))
      const checkbox = attrs.type === 'checkbox'
      return h(props.kind, { ...attrs, ref:field, value: checkbox ? undefined : props.modelValue, checked: checkbox ? !!props.modelValue : undefined,
        onInput: event => { if (!checkbox) emit('update:modelValue', event.target.value) },
        onChange: event => { const value = checkbox ? event.target.checked : event.target.value; emit('update:modelValue', value); emit('change', value) },
        onKeydown: event => { if (event.key === 'Enter' && props.kind !== 'textarea') { event.preventDefault(); emit('confirm') } }
      }, props.kind === 'select' ? (props.options || []).map(item => h('option', { value: item.value }, item.label)) : undefined)
    }
  }
})
// #endif
