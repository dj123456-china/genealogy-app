<template>
<view class="app-dialog family-guide-dialog el-dialog" role="dialog" aria-modal="true" aria-labelledby="familyGuideHeading" :aria-busy="busy" @click.stop>
  <view class="dialog-header">
    <view><NativeText class="eyebrow dark">{{mode==='invite'?'选择家谱':'家谱使用导览'}}</NativeText><view class="el-h2" id="familyGuideHeading">{{heading}}</view></view>
    <NativeButton v-if="mode!=='invite'" :disabled="busy" @click="perform('close')" class="icon-btn el-button" aria-label="关闭导览"><NativeText class="ph ph-x" aria-hidden="true"/></NativeButton>
  </view>
  <view v-if="displayError" class="guide-error" role="alert">{{displayError}}</view>
  <view v-if="busy" class="guide-progress" role="status">正在处理，请稍候…</view>

  <template v-if="mode==='invite'">
    <view class="guide-intro">手机号已验证。你可以进入自己的家谱，也可以使用亲友给你的邀请码加入他们的家谱。</view>
    <view class="guide-choices" aria-label="是否有家族邀请码">
      <NativeButton class="guide-choice el-button" :class="{active:choice==='personal'}" :aria-pressed="choice==='personal'" :disabled="busy" @click="choose('personal')"><NativeText class="ph ph-house" aria-hidden="true"/><NativeText class="guide-choice-copy"><NativeText class="el-strong">没有邀请码</NativeText><NativeText class="el-small">先整理自己的家谱</NativeText></NativeText></NativeButton>
      <NativeButton class="guide-choice el-button" :class="{active:choice==='join'}" :aria-pressed="choice==='join'" :disabled="busy" @click="choose('join')"><NativeText class="ph ph-users-three" aria-hidden="true"/><NativeText class="guide-choice-copy"><NativeText class="el-strong">已有邀请码</NativeText><NativeText class="el-small">加入亲友的家谱</NativeText></NativeText></NativeButton>
    </view>
    <template v-if="choice==='join'">
      <view class="guide-code-label"><NativeText class="el-strong">6 位家族邀请码</NativeText><NativeField id="guideInviteCode" class="el-input guide-code-field" type="text" inputmode="numeric" maxlength="6" autocomplete="off" placeholder="例如：012345" aria-label="6 位家族邀请码" v-model="code" :disabled="busy" @confirm="submitCode"/></view>
      <view class="form-hint">这是管理员提供的家族邀请码，与登录短信验证码不同。邀请码 7 天内有效，仅能使用一次。</view>
      <view class="guide-note">加入后的权限由管理员决定。你的个人家谱会保留，可随时在“我的”中切换回来。</view>
      <view class="guide-invite-actions"><NativeButton class="btn btn-secondary el-button" :disabled="busy" @click="perform('personal')">进入我的家谱</NativeButton><NativeButton class="btn btn-primary el-button" :disabled="busy || !code.trim()" @click="submitCode">{{busy?'请稍候…':'验证邀请码并加入'}}</NativeButton></view>
    </template>
    <template v-else>
      <view class="guide-note">自己的家谱独立保存成员、关系和纪念日。以后也可以在“我的”输入邀请码，加入亲友的家谱。</view>
      <view class="guide-invite-actions"><NativeButton class="btn btn-primary el-button" :disabled="busy" @click="perform('personal')">{{busy?'请稍候…':'进入我的家谱'}}</NativeButton></view>
    </template>
  </template>

  <template v-else>
    <view class="guide-intro">{{mode==='library'?'所有使用说明集中在这里。关闭自动导览后，仍可随时从“我的”重新查看。':'从录入家人到邀请亲友一起维护，你可以按下面的步骤开始使用。'}}</view>
    <view class="guide-topics">
      <view v-for="(topic,index) in visibleTopics" :key="topic.id" class="guide-topic">
        <NativeText class="guide-topic-number" aria-hidden="true">{{String(index+1).padStart(2,'0')}}</NativeText>
        <view class="guide-topic-content"><view class="guide-topic-title"><NativeText class="ph" :class="topic.icon" aria-hidden="true"/><NativeText class="el-strong">{{topic.title}}</NativeText></view><view class="guide-topic-description">{{topic.description}}</view><NativeButton v-if="topic.action" class="text-btn guide-topic-action el-button" :disabled="busy" @click="perform('navigate',topic.action)">{{topic.button}}<NativeText class="ph ph-arrow-right" aria-hidden="true"/></NativeButton></view>
      </view>
    </view>
    <view class="guide-preferences">
      <NativeText class="el-strong">自动导览设置</NativeText>
      <view class="form-hint">今日关闭按北京时间计算，明天恢复；永久关闭后可在“我的 → 我的所有导览”查看或恢复。手机号登录后的邀请码询问仍会显示。</view>
      <view class="guide-preference-actions"><NativeButton class="btn btn-secondary el-button" :disabled="busy" @click="perform('dismiss','today')">今日关闭</NativeButton><NativeButton class="btn btn-secondary el-button" :disabled="busy" @click="perform('dismiss','permanent')">永久关闭</NativeButton><NativeButton v-if="mode==='library'" class="btn btn-primary el-button" :disabled="busy" @click="perform('reset')">恢复每次登录导览</NativeButton></view>
    </view>
    <view class="guide-footer"><NativeButton class="btn btn-primary el-button" :disabled="busy" @click="perform('close')">{{mode==='library'?'关闭使用说明':'开始使用'}}</NativeButton></view>
  </template>
</view>
</template>

<script setup>
// #ifdef H5
import NativeText from './NativeText.h5.js'
import NativeButton from './NativeButton.h5.js'
import NativeField from './NativeField.h5.js'
// #endif
// #ifndef H5
import NativeText from './NativeText.vue'
import NativeButton from './NativeButton.vue'
import NativeField from './NativeField.vue'
// #endif
import {computed,ref,watch} from 'vue'
import {validateInviteCode} from '../../utils/family-sharing.js'

const props=defineProps({mode:{type:String,default:'tour'},busy:Boolean,error:{type:String,default:''}})
const emit=defineEmits(['join','personal','dismiss','close','reset','navigate'])
const choice=ref('personal'),code=ref(''),localError=ref('')
const heading=computed(()=>props.mode==='invite'?'您有家族邀请码吗？':props.mode==='library'?'我的所有导览':'开始使用家谱制作器')
const displayError=computed(()=>localError.value||props.error)
const topics=[
  {id:'invite',icon:'ph-user-plus',title:'邀请亲友与分配权限',description:'在“我的”生成 6 位邀请码，选择只读或可编辑权限。管理员拥有全部管理权限，可撤销邀请码、调整协作者权限或移除协作者；普通协作者不能修改管理员身份。',action:'invite',button:'查看邀请入口'},
  {id:'join',icon:'ph-users-three',title:'使用邀请码加入家谱',description:'手机号登录后可填写邀请码，也可在“我的”输入邀请码加入。邀请码与短信验证码不同；加入已有资格的家谱时，原权限不会自动升级。加入前请先同步当前家谱的修改。',action:'join',button:'输入家族邀请码'},
  {id:'personal',icon:'ph-house',title:'切换家谱或返回自己的家谱',description:'“我的”列出自己的家谱和已加入的家谱。成员、关系和纪念日分别保存，切换不会把个人资料并入亲友家谱；可随时返回自己的家谱。',action:'personal',button:'返回自己的家谱'},
  {id:'members',icon:'ph-tree-structure',title:'录入成员与真实关系',description:'添加姓名、性别、出生日期与世代，再选择父亲、母亲和配偶建立关系。家族树、成员名录支持搜索；选择两位成员可分析已录入的关系。只读协作者可浏览，管理员和可编辑协作者可维护资料。'},
  {id:'reminders',icon:'ph-calendar-dots',title:'记录生日、忌日与祭日',description:'添加成员时可同时创建生日或忌日提醒，也可单独添加、编辑纪念日。选择公历、农历或清明节气，设置提前提醒和每年重复；服务端生成的通知可在收件箱查看。'},
  {id:'backup',icon:'ph-download-simple',title:'同步与备份家谱',description:'保存后查看同步状态；断网时资料保留本机，联网后继续同步。发生修改冲突时可查看双方资料并选择处理。通过“我的 → 导入导出”保存包含头像图片的 JSON 备份；导入会替换当前家谱，建议先导出备份。'},
  {id:'notifications',icon:'ph-bell',title:'通知与隐私授权',description:'通过通知入口查看收件箱、标记已读。在“我的 → 隐私授权”管理站内提醒和系统通知。系统通知还需设备授权，实际后台投递能力可在通知通道状态查看。'},
  {id:'account',icon:'ph-shield-check',title:'账户、登录设备与旧资料',description:'在“我的”绑定手机号、管理登录设备并查看操作日志。导入导出中可迁移原设备保存的旧本机账号资料。注销账号会永久删除账号及其拥有的家谱，操作前可先保存备份。'}
]
const visibleTopics=computed(()=>props.mode==='library'?topics:topics.slice(0,6))

function choose(value){if(props.busy)return;choice.value=value;localError.value=''}
function perform(event,value){if(props.busy)return;localError.value='';emit(event,value)}
function submitCode(){
  if(props.busy)return
  try{const normalized=validateInviteCode(code.value);localError.value='';emit('join',normalized)}
  catch(error){localError.value=error.message}
}
watch(code,()=>localError.value='')
watch(()=>props.mode,()=>{choice.value='personal';code.value='';localError.value=''})
</script>

<style scoped>
.family-guide-dialog { width:calc(100vw - 32px); max-width:760px; max-height:calc(100vh - 36px); padding:28px; }
.guide-intro { font-size:13px; line-height:1.85; color:var(--muted); margin-bottom:20px; }
.guide-error { margin:0 0 16px; padding:11px 14px; border:1px solid rgba(139,47,42,.25); background:#fff6f4; color:var(--brand); font-size:13px; line-height:1.7; }
.guide-progress { margin-bottom:14px; font-size:12px; color:var(--muted); }
.guide-choices { display:flex; gap:14px; margin:20px 0; }
.guide-choice { display:flex; align-items:center; flex:1; width:0; min-height:88px; padding:16px; gap:12px; border:1px solid var(--line); border-radius:var(--radius-control); background:var(--surface-strong); text-align:left; }
.guide-choice.active { border-color:var(--brand); background:var(--brand-soft); color:var(--brand); }
.guide-choice > .ph { font-size:24px; flex-shrink:0; }
.guide-choice-copy,.guide-choice-copy .el-strong,.guide-choice-copy .el-small { display:block; }
.guide-choice-copy .el-strong { font-size:14px; }
.guide-choice-copy .el-small { font-size:11px; color:var(--muted); margin-top:5px; }
.guide-code-label { display:flex; flex-direction:column; gap:9px; margin:20px 0 9px; font-size:12px; }
.guide-code-field { width:100%; min-height:50px; padding:12px 15px; border:1px solid var(--line); background:var(--surface-strong); color:var(--ink); border-radius:var(--radius-control); font-size:20px; letter-spacing:.18em; font-variant-numeric:tabular-nums; }
.guide-note { margin:20px 0 0; padding:14px 16px; border-left:2px solid var(--brand); background:var(--surface-strong); color:var(--muted); font-size:12px; line-height:1.8; }
.guide-invite-actions { display:flex; justify-content:flex-end; gap:10px; flex-wrap:wrap; margin-top:24px; }
.guide-topics { border-top:1px solid var(--line); }
.guide-topic { display:flex; align-items:flex-start; gap:15px; padding:19px 0; border-bottom:1px solid var(--line); }
.guide-topic-number { display:block; flex-shrink:0; width:32px; height:32px; line-height:30px; text-align:center; border:1px solid rgba(139,47,42,.3); color:var(--brand); font-size:13px; }
.guide-topic-content { flex:1; min-width:0; }
.guide-topic-title { display:flex; align-items:center; gap:8px; margin:3px 0 7px; font-size:14px; }
.guide-topic-title .ph { color:var(--brand); font-size:17px; }
.guide-topic-description { color:var(--muted); font-size:12px; line-height:1.9; }
.guide-topic-action { display:inline-flex; align-items:center; gap:7px; margin-top:10px; font-size:12px; }
.guide-preferences { margin-top:22px; padding:16px; background:var(--surface-strong); border:1px solid var(--line); }
.guide-preferences > .el-strong { display:block; margin-bottom:8px; font-size:13px; }
.guide-preference-actions { display:flex; flex-wrap:wrap; gap:9px; margin-top:15px; }
.guide-preference-actions .btn { font-size:12px; }
.guide-footer { display:flex; justify-content:flex-end; margin-top:20px; }
@media (max-width:600px) {
  .family-guide-dialog { padding:22px 18px; max-height:calc(100vh - 28px); }
  .dialog-header .el-h2 { font-size:23px; }
  .guide-choices { flex-direction:column; gap:10px; }
  .guide-choice { width:100%; flex:auto; min-height:74px; padding:13px 14px; }
  .guide-topic { gap:11px; padding:17px 0; }
  .guide-topic-number { width:28px; height:28px; line-height:26px; font-size:12px; }
  .guide-topic-title { font-size:13px; }
  .guide-invite-actions,.guide-footer { flex-direction:column; }
  .guide-invite-actions .btn,.guide-footer .btn { width:100%; }
  .guide-preferences { padding:14px; }
  .guide-preference-actions .btn { flex:1; min-width:120px; }
}
</style>
