<template>
<view class="family-sharing" id="familySharing" aria-labelledby="familySharingHeading">
  <view class="sharing-heading">
    <view><NativeText class="eyebrow dark">家谱协作</NativeText><view class="el-h3" id="familySharingHeading">邀请、加入与切换家谱</view><view class="form-hint">当前：{{store.profile.name}} · {{roleLabel(store.role)}}</view></view>
    <NativeButton :disabled="blocked" class="btn btn-secondary btn-small" @click="load()">刷新</NativeButton>
  </view>
  <view v-if="!eligible" class="form-hint">登录后可生成邀请码、加入亲友家谱，并随时返回自己的家谱。</view>
  <template v-else>
    <view v-if="error" class="sharing-error" role="alert">{{error}}</view>
    <view v-if="message" class="sharing-message" role="status">{{message}}</view>
    <view v-if="loading" class="form-hint">正在读取家谱与协作者…</view>
    <view class="sharing-panels">
      <view class="sharing-panel" id="familyInvite">
        <view class="sharing-title"><NativeText class="ph ph-user-plus" aria-hidden="true"/><view class="el-h4">邀请亲友</view></view>
        <template v-if="isOwner">
          <view class="form-hint">你是管理员，拥有当前家谱的全部权限。为亲友选择只读或可编辑权限，管理员身份不会转让。</view>
          <view class="sharing-field"><NativeText>受邀者权限</NativeText><NativeField class="el-select" kind="select" v-model="inviteRole" :options="roleOptions" :disabled="blocked" aria-label="邀请码权限"/></view>
          <NativeButton class="btn btn-primary" :disabled="blocked" @click="generateCode">{{busy?'请稍候…':'生成 6 位邀请码'}}</NativeButton>
          <view v-if="latestCode" class="sharing-new-code"><NativeText class="form-hint">新邀请码 · {{roleLabel(latestCode.role)}}</NativeText><NativeText class="sharing-code" selectable>{{latestCode.code}}</NativeText><NativeButton class="btn btn-secondary btn-small" :disabled="blocked" @click="copyCode(latestCode)">复制邀请码</NativeButton></view>
          <view class="form-hint">邀请码 7 天内有效，仅可使用一次。请将代码交给要加入的亲友。</view>
          <view v-if="codes.length" class="sharing-code-list"><view v-for="item in codes" :key="item.id" class="sharing-code-row"><view><NativeText class="sharing-code-small" selectable>{{item.code}}</NativeText><view class="form-hint">{{roleLabel(item.role)}} · {{codeStatus(item)}}<NativeText class="sharing-expiry">{{formatTime(item.expires_at)}} 到期</NativeText></view></view><view class="sharing-row-actions"><NativeButton v-if="isPending(item)" :disabled="blocked" class="text-btn" @click="copyCode(item)">复制</NativeButton><NativeButton v-if="isPending(item)" :disabled="blocked" class="text-btn sharing-danger" @click="revokeCode(item)">撤销</NativeButton></view></view></view>
          <view v-else-if="!loading" class="form-hint">还没有生成邀请码。</view>
        </template>
        <view v-else class="form-hint">当前权限为{{roleLabel(store.role)}}。只有该家谱的管理员可以生成或撤销邀请码、修改协作者权限。可先返回自己的家谱，再邀请亲友加入。</view>
      </view>
      <view class="sharing-panel" id="familyJoin">
        <view class="sharing-title"><NativeText class="ph ph-users-three" aria-hidden="true"/><view class="el-h4">加入亲友家谱</view></view>
        <view class="form-hint">输入亲友提供的 6 位数字邀请码。加入后的访问权限由管理员决定，你自己的家谱会保留。</view>
        <view class="sharing-field"><NativeText>家族邀请码</NativeText><NativeField id="familyJoinCode" class="el-input sharing-code-input" type="text" inputmode="numeric" maxlength="6" autocomplete="off" placeholder="请输入 6 位数字" aria-label="家族邀请码" v-model="joinCode" :disabled="blocked" @confirm="joinCodeFamily"/></view>
        <NativeButton :disabled="blocked || !validCode" class="btn btn-primary" @click="joinCodeFamily">{{busy?'请稍候…':'验证邀请码并加入'}}</NativeButton>
        <view class="form-hint">家族邀请码与登录短信验证码不同，加入前须同步当前家谱的修改。</view>
      </view>
    </view>
    <view class="sharing-families" id="familySwitch">
      <view class="sharing-heading"><view><view class="el-h4">我的家谱与已加入的家谱</view><view class="form-hint">每个家谱独立保存成员、关系和纪念日，切换时只显示所选家谱。</view></view><NativeButton :disabled="blocked || isPersonal" class="btn btn-secondary btn-small" @click="returnPersonal">{{isPersonal?'已在自己的家谱':'返回自己的家谱'}}</NativeButton></view>
      <view v-for="family in families" :key="family.id" class="sharing-family-row"><view><NativeText class="el-strong">{{family.name}}</NativeText><view class="form-hint">{{isOwnFamily(family)?'自己的家谱':'已加入的家谱'}} · {{roleLabel(family.role)}}{{Number(family.id)===Number(store.familyId)?' · 当前':''}}</view></view><NativeButton :disabled="blocked || Number(family.id)===Number(store.familyId)" class="btn btn-secondary btn-small" @click="activateFamily(family)">{{Number(family.id)===Number(store.familyId)?'当前家谱':'切换'}}</NativeButton></view>
      <view v-if="!families.length && !loading" class="form-hint">暂未读取到家谱，可点击刷新重试。</view>
    </view>
    <view class="sharing-members">
      <view class="el-h4">当前家谱协作者</view><view class="form-hint">管理员可维护家谱及所有协作设置；可编辑成员可维护档案和提醒；只读成员可浏览。</view>
      <view v-for="member in memberships" :key="member.id" class="sharing-member-row"><view><NativeText class="el-strong">{{member.username}}</NativeText><view class="form-hint">{{roleLabel(member.role)}}{{member.role==='OWNER'?' · 全部权限':''}}{{Number(member.user_id)===Number(store.user?.id)?' · 我':''}}</view></view><view v-if="isOwner && member.role!=='OWNER'" class="sharing-member-controls"><NativeField class="el-select" kind="select" :options="roleOptions" v-model="memberRoles[member.id]" :disabled="blocked" :aria-label="member.username+'的权限'"/><NativeButton class="btn btn-secondary btn-small" :disabled="blocked || memberRoles[member.id]===member.role" @click="saveRole(member)">保存权限</NativeButton><NativeButton class="text-btn sharing-danger" :disabled="blocked" @click="removeCollaborator(member)">移除</NativeButton></view></view>
      <view v-if="!memberships.length && !loading" class="form-hint">暂无协作者记录。</view>
    </view>
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
import {ref, reactive, computed, watch, nextTick, onUnmounted} from 'vue'
import {store, authenticatedRequest, switchFamily} from '../../utils/store.js'
import {listFamilies, listInviteCodes, createInviteCode, revokeInviteCode, joinFamilyByCode, returnToPersonalFamily, normalizeInviteCode, validateInviteCode} from '../../utils/family-sharing.js'
const props=defineProps({active:{type:Boolean,default:true}}),emit=defineEmits(['toast','changed'])
const families=ref([]),memberships=ref([]),codes=ref([]),latestCode=ref(null),inviteRole=ref('VIEWER'),joinCode=ref(''),memberRoles=reactive({})
const busy=ref(false),loading=ref(false),error=ref(''),message=ref('')
const eligible=computed(()=>!!store.session?.accessToken&&store.sessionValidated&&!store.guest),isOwner=computed(()=>store.role==='OWNER')
const blocked=computed(()=>busy.value||loading.value||!eligible.value||['loading','saving'].includes(store.syncStatus))
const validCode=computed(()=>/^\d{6}$/.test(normalizeInviteCode(joinCode.value)))
const isOwnFamily=family=>Number(family.owner_id)===Number(store.user?.id)
const isPersonal=computed(()=>families.value.some(f=>Number(f.id)===Number(store.familyId)&&isOwnFamily(f)))
const roleOptions=[{value:'VIEWER',label:'只读 · 查看家谱'},{value:'EDITOR',label:'可编辑 · 维护档案和提醒'}]
const roleLabel=role=>({OWNER:'管理员',EDITOR:'可编辑',VIEWER:'只读'})[role]||'权限待确认'
const asDate=value=>new Date(/Z$|[+-]\d{2}:?\d{2}$/.test(value||'')?value:String(value||'')+'Z')
const formatTime=value=>value?asDate(value).toLocaleString('zh-CN'):'有效期未记录'
const isPending=item=>item.status==='PENDING'&&(!item.expires_at||asDate(item.expires_at).getTime()>Date.now())
const codeStatus=item=>item.status==='PENDING'&&!isPending(item)?'已过期':({PENDING:'待使用',USED:'已使用',ACCEPTED:'已使用',REVOKED:'已撤销',CANCELLED:'已撤销',EXPIRED:'已过期'})[item.status]||item.status
const accountIdentity=()=>[store.session?.accountId,store.session?.accessToken].join('|'),contextIdentity=()=>accountIdentity()+'|'+store.familyId
let generation=0,alive=true
function assertAccount(identity){if(!alive||identity!==accountIdentity())throw Error('账号已切换，请重新操作。')}
function assertContext(identity){if(!alive||identity!==contextIdentity())throw Error('账号或家谱已切换，请重新操作。')}
async function load(){
  if(!eligible.value)return
  const sequence=++generation,identity=contextIdentity(),owner=isOwner.value
  loading.value=true;error.value=''
  const requests=[listFamilies(),authenticatedRequest('/family/memberships'),...(owner?[listInviteCodes()]:[])]
  const results=await Promise.allSettled(requests)
  if(!alive||sequence!==generation||identity!==contextIdentity())return
  const failures=[]
  results.forEach((result,index)=>{if(result.status==='rejected'){failures.push(result.reason?.message||'读取失败');return};if(index===0)families.value=result.value;if(index===1){memberships.value=result.value;Object.keys(memberRoles).forEach(key=>delete memberRoles[key]);result.value.forEach(member=>memberRoles[member.id]=member.role)};if(index===2){codes.value=result.value;if(latestCode.value){const currentCode=result.value.find(item=>item.id===latestCode.value.id);latestCode.value=currentCode&&isPending(currentCode)?currentCode:null}}})
  if(!owner)codes.value=[]
  error.value=[...new Set(failures)].join('；');loading.value=false
}
async function run(action,successMessage){
  if(blocked.value)return
  const identity=accountIdentity(),context=contextIdentity()
  busy.value=true;error.value='';message.value=''
  try{const result=await action(()=>assertContext(context));assertAccount(identity);if(result?.synced===false)throw Error('已切换家谱，资料尚未完成同步。请查看同步状态并处理后重试。');message.value=successMessage;emit('toast',successMessage);emit('changed')}
  catch(e){if(alive&&identity===accountIdentity())error.value=e.message}
  finally{if(alive&&identity===accountIdentity()){const actionError=error.value;await load();if(actionError)error.value=actionError;busy.value=false}}
}
function generateCode(){return run(async check=>{const result=await createInviteCode(inviteRole.value);check();latestCode.value=result},'邀请码已生成')}
function joinCodeFamily(){return run(async()=>{const result=await joinFamilyByCode(validateInviteCode(joinCode.value));joinCode.value='';return result},'已加入亲友家谱，你自己的家谱已保留')}
function activateFamily(family){return run(()=>switchFamily(family.id),'已切换家谱')}
function returnPersonal(){return run(returnToPersonalFamily,'已返回自己的家谱')}
async function confirmAction(title,content){const identity=contextIdentity();const confirmed=await new Promise(resolve=>uni.showModal({title,content,confirmText:'确认',success:r=>resolve(!!r.confirm),fail:()=>resolve(false)}));assertContext(identity);return confirmed}
function revokeCode(item){return run(async check=>{if(!await confirmAction('撤销邀请码',`撤销 ${item.code} 后，亲友将无法用它加入当前家谱，确认继续？`))throw Error('已取消撤销');check();await revokeInviteCode(item.id);check();if(latestCode.value?.id===item.id)latestCode.value=null},'邀请码已撤销')}
function saveRole(member){return run(async check=>{const role=memberRoles[member.id];if(!await confirmAction('修改协作者权限',`将 ${member.username} 改为${roleLabel(role)}，确认继续？`))throw Error('已取消修改');check();await authenticatedRequest(`/family/memberships/${member.id}`,{method:'PATCH',data:{role}})},'协作者权限已保存')}
function removeCollaborator(member){return run(async check=>{if(!await confirmAction('移除协作者',`移除 ${member.username} 后，对方将无法访问当前家谱，确认继续？`))throw Error('已取消移除');check();await authenticatedRequest(`/family/memberships/${member.id}`,{method:'DELETE'})},'协作者已移除')}
function copyCode(item){if(blocked.value)return;const identity=contextIdentity();uni.setClipboardData({data:item.code,success:()=>{if(identity===contextIdentity()){message.value='邀请码已复制';emit('toast','邀请码已复制')}},fail:()=>{if(identity===contextIdentity())error.value='复制失败，请手动选中邀请码复制。'}})}
async function navigate(action){
  if(busy.value)return
  if(loading.value)await load()
  if(action==='personal'){await returnPersonal();return}
  await nextTick()
  const id=action==='invite'?'familyInvite':'familyJoin'
  uni.pageScrollTo({selector:'#'+id,duration:200})
  // #ifdef H5
  document.getElementById(id)?.scrollIntoView({block:'center',behavior:'smooth'})
  if(action==='join')document.getElementById('familyJoinCode')?.focus({preventScroll:true})
  // #endif
}
watch(()=>[props.active,eligible.value,contextIdentity(),store.role],()=>{generation++;loading.value=false;families.value=[];memberships.value=[];codes.value=[];latestCode.value=null;joinCode.value='';error.value='';message.value='';if(props.active&&eligible.value&&!busy.value)load()},{immediate:true})
watch(accountIdentity,()=>{busy.value=false})
onUnmounted(()=>{alive=false;generation++})
defineExpose({navigate,busy})
</script>
<style scoped>
.family-sharing{margin:22px 0;background:var(--surface-strong,#fffdf8);border:1px solid var(--line,#d9d0c7);padding:24px;color:var(--ink,#3d342d)}
.sharing-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.sharing-heading .el-h3{font-family:"STSong","Songti SC",serif;font-size:25px;margin:6px 0}.sharing-heading>.btn{flex-shrink:0}
.sharing-panels{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:22px;margin-top:18px}.sharing-panel{border:1px solid var(--line,#d9d0c7);padding:20px;min-width:0}.sharing-title{display:flex;gap:9px;align-items:center}.sharing-title>.ph{font-size:22px;color:var(--brand,#8b2f2a)}.el-h4{font-size:16px;font-weight:700}.sharing-field{display:flex;flex-direction:column;gap:7px;margin:16px 0;font-size:12px}.sharing-field .el-input,.sharing-field .el-select,.sharing-member-controls .el-select{min-width:0;width:100%;min-height:42px;background:var(--surface-strong,#fffdf8);border:1px solid var(--line,#d9d0c7);padding:9px 11px;color:inherit}.sharing-code-input{font-size:20px;letter-spacing:.18em}.sharing-panel>.btn{width:100%}.sharing-new-code{margin-top:18px;background:var(--brand-soft,#ead9d5);padding:14px;display:flex;align-items:center;flex-wrap:wrap;gap:12px}.sharing-new-code>.form-hint{width:100%;margin:0}.sharing-code{font-size:30px;letter-spacing:.15em;color:var(--brand,#8b2f2a);font-variant-numeric:tabular-nums}.sharing-code-small{font-size:19px;letter-spacing:.12em;font-variant-numeric:tabular-nums}.sharing-code-row,.sharing-family-row,.sharing-member-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:13px 0;border-top:1px solid var(--line,#d9d0c7)}.sharing-code-row:first-child{margin-top:16px}.sharing-code-row .form-hint,.sharing-family-row .form-hint,.sharing-member-row .form-hint{margin:4px 0 0}.sharing-expiry{display:block}.sharing-row-actions{display:flex;gap:12px;flex-shrink:0}.sharing-danger{color:var(--brand,#8b2f2a)}.sharing-families,.sharing-members{margin-top:24px;padding-top:22px;border-top:1px solid var(--line,#d9d0c7)}.sharing-member-controls{display:flex;gap:10px;align-items:center}.sharing-member-controls .el-select{width:190px;font-size:12px}.sharing-family-row>.btn,.sharing-member-controls>.btn{flex-shrink:0}.sharing-error,.sharing-message{padding:12px 14px;margin-top:14px;font-size:13px;line-height:1.6;border:1px solid var(--line,#d9d0c7)}.sharing-error{color:var(--brand,#8b2f2a);background:var(--brand-soft,#ead9d5)}.sharing-message{background:var(--surface-muted,#ede9e3)}
@media(max-width:760px){.family-sharing{padding:18px;margin:16px 0}.sharing-heading{flex-wrap:wrap;gap:10px}.sharing-heading .el-h3{font-size:22px}.sharing-panels{grid-template-columns:1fr;gap:15px}.sharing-panel{padding:16px}.sharing-member-row{align-items:flex-start;flex-wrap:wrap}.sharing-member-controls{width:100%;flex-wrap:wrap}.sharing-member-controls .el-select{flex:1;min-width:130px}.sharing-families .sharing-heading>.btn{width:100%}.sharing-code-row{align-items:flex-start}.sharing-row-actions{gap:6px}}
</style>
