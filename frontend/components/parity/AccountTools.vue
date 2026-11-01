<template>
<view class="app-dialog tools-dialog el-dialog" role="dialog" aria-modal="true" aria-labelledby="toolsHeading" @click.stop>
<view class="dialog-header"><view><NativeText class="eyebrow dark">{{store.guest?'访客模式':'账户与协作'}}</NativeText><view class="el-h2" id="toolsHeading">{{ visibleTabs.find(t=>t.id===tab)?.label }}</view></view><NativeButton :disabled="busy" @click="$emit('close')" class="icon-btn" aria-label="关闭"><NativeText class="ph ph-x" /></NativeButton></view>
<view v-if="visibleTabs.length>1" class="tools-tabs" role="tablist"><NativeButton v-for="item in visibleTabs" :key="item.id" :class="{active:tab===item.id}" :aria-selected="tab===item.id" role="tab" :disabled="busy" @click="tab=item.id">{{item.label}}</NativeButton></view>
<view v-if="!store.guest&&error" class="tools-error" role="alert">{{error}}</view><view v-if="!store.guest&&message" class="tools-message" role="status">{{message}}</view>
<view v-if="!store.guest&&loading" class="form-hint">正在读取服务端资料…</view>
<template v-else-if="store.guest">
<view class="guest-guide">
<view class="guest-guide-intro"><NativeText class="ph ph-eye guest-guide-icon" aria-hidden="true" /><view><view class="el-h3">访客浏览模式</view><view class="form-hint">无需登录即可查看示范内容。当前资料仅供浏览，所有编辑和账户操作均已关闭。</view></view></view>
<view class="el-h3 tools-section-title">现在可以使用</view>
<view class="guest-guide-list"><view><NativeText class="ph ph-tree-structure" /><NativeText><NativeText class="el-strong">浏览家族树和成员名录</NativeText><NativeText class="form-hint">查看成员关系、资料卡片和示范族谱。</NativeText></NativeText></view><view><NativeText class="ph ph-magnifying-glass" /><NativeText><NativeText class="el-strong">搜索和关系分析</NativeText><NativeText class="form-hint">按姓名或关系查找成员，选择两人查看关系。</NativeText></NativeText></view><view><NativeText class="ph ph-calendar-dots" /><NativeText><NativeText class="el-strong">查看纪念日和节气</NativeText><NativeText class="form-hint">浏览生日、忌日、传统祭日和农历信息。</NativeText></NativeText></view></view>
<view class="guest-login-note"><NativeText class="ph ph-lock-key" /><view><NativeText class="el-strong">登录后可使用完整功能</NativeText><view class="form-hint">新增、编辑和删除成员与提醒；同步、备份、家族协作、隐私授权及登录设备管理。</view></view></view>
</view>
</template>
<template v-else-if="tab==='notifications'">
<view class="tools-heading"><NativeText class="form-hint">未读 {{unread}} 条 · 通知记录由服务端定时生成</NativeText><NativeButton class="btn btn-secondary btn-small" :disabled="busy||!unread" @click="markAllRead">全部已读</NativeButton></view>
<view v-if="!notifications.length" class="tools-empty">暂无通知</view>
<NativeButton v-for="notice in notifications" :key="notice.id" class="tools-record notice-record" :class="{'notice-unread':!notice.read_at}" :disabled="busy" @click="markRead(notice)"><view><NativeText class="el-strong">{{notice.title}}</NativeText><view class="el-p">{{notice.body}}</view><NativeText class="el-small">{{formatTime(notice.created_at)}} · {{notice.read_at?'已读':'点击标为已读'}}</NativeText></view></NativeButton>
</template>
<template v-else-if="tab==='privacy'">
<view class="form-hint">资料存储于服务器及当前设备缓存，具有此家族成员资格的账号可按权限访问。邀请在应用内送达，不会发送外部短信或邮件。</view>
<view class="tools-switch"><NativeField type="checkbox" v-model="preferences.notifications_enabled" :disabled="busy"/><view><NativeText class="el-strong">站内提醒</NativeText><view class="form-hint">开启后，服务端生成生日、忌日与祭日通知。</view></view></view>
<view class="tools-switch"><NativeField type="checkbox" v-model="preferences.system_notifications_enabled" :disabled="busy"/><view><NativeText class="el-strong">系统通知</NativeText><view class="form-hint">还需授予设备通知权限。后台投递以当前服务器能力为准。</view></view></view>
<view v-if="permissionMessage" class="form-hint">{{permissionMessage}}</view>
<view class="tools-record"><NativeText class="el-strong">通知通道状态</NativeText><view v-for="(value,key) in deliveryStatus" :key="key" class="form-hint">{{channelLabel(key)}}：{{statusText(value)}}</view></view>
<view class="tools-actions"><NativeButton class="btn btn-secondary" :disabled="busy" @click="requestPermission">申请设备通知权限</NativeButton><NativeButton class="btn btn-primary" :disabled="busy" @click="savePreferences">保存授权设置</NativeButton></view>
</template>
<template v-else-if="tab==='phone'">
<view class="form-hint">当前手机号：{{store.user?.phone||'未绑定'}}。绑定或更换手机号需要短信验证。</view>
<view class="form-grid"><view class="el-label"><NativeText>新手机号</NativeText><NativeField v-model="phoneForm.phone" type="tel" maxlength="11" class="el-input" :disabled="busy" placeholder="请输入 11 位手机号"/></view><view class="el-label"><NativeText>验证码</NativeText><NativeField v-model="phoneForm.smsCode" type="tel" maxlength="6" class="el-input" :disabled="busy" placeholder="6 位短信验证码"/></view></view>
<view class="tools-actions"><NativeButton class="btn btn-secondary" :disabled="busy||!!smsCountdown" @click="sendPhoneCode">{{smsCountdown?smsCountdown+' 秒后重发':'获取验证码'}}</NativeButton><NativeButton class="btn btn-primary" :disabled="busy" @click="bindPhone">验证并保存手机号</NativeButton></view>
</template>
<template v-else-if="tab==='sessions'">
<view class="form-hint">可撤销任意登录设备的会话。撤销当前设备后需要重新登录。</view>
<view v-for="session in sessions" :key="session.id" class="tools-record tools-heading"><view><NativeText class="el-strong">{{session.current?'当前设备':'其他登录会话'}} #{{session.id}}</NativeText><view class="form-hint">登录 {{formatTime(session.created_at)}}<br/>到期 {{formatTime(session.expires_at)}}</view></view><NativeButton class="btn btn-secondary btn-small" :disabled="busy" @click="revokeSession(session)">撤销</NativeButton></view>
<view v-if="!sessions.length" class="tools-empty">暂无有效会话</view>
</template>
<template v-else-if="tab==='families'">
<view class="form-hint">切换后只显示所选家族的资料。当前家族：{{store.profile.name}}（{{roleLabel(store.role)}}）</view>
<view v-for="family in families" :key="family.id" class="tools-record tools-heading"><view><NativeText class="el-strong">{{family.name}}</NativeText><view class="form-hint">{{roleLabel(family.role)}}{{String(family.id)===String(store.familyId)?' · 当前家族':''}}</view></view><NativeButton class="btn btn-secondary btn-small" :disabled="busy||String(family.id)===String(store.familyId)" @click="activateFamily(family)">切换</NativeButton></view>
<view class="el-h3 tools-section-title">收到的邀请</view><view v-if="!incoming.length" class="tools-empty">暂无待处理邀请</view>
<view v-for="invite in incoming" :key="invite.id" class="tools-record"><NativeText class="el-strong">{{invite.family_name}} · {{roleLabel(invite.role)}}</NativeText><view class="form-hint">{{inviteStatus(invite.status)}}</view><view v-if="String(invite.status).toUpperCase()==='PENDING'" class="tools-actions"><NativeButton class="btn btn-primary btn-small" :disabled="busy" @click="respondInvite(invite,true)">接受并进入</NativeButton><NativeButton class="btn btn-secondary btn-small" :disabled="busy" @click="respondInvite(invite,false)">拒绝</NativeButton></view></view>
</template>
<template v-else-if="tab==='collaboration'">
<view v-if="isOwner" class="form-grid"><view class="el-label"><NativeText>邀请现有账号</NativeText><NativeField class="el-input" v-model="invitation.invitee" :disabled="busy" placeholder="对方登录名或手机号" maxlength="32"/></view><view class="el-label"><NativeText>权限</NativeText><NativeField class="el-select" kind="select" v-model="invitation.role" :options="roleOptions" :disabled="busy"/></view><NativeButton class="btn btn-primary" :disabled="busy" @click="inviteMember">发出站内邀请</NativeButton></view>
<view v-else class="form-hint">仅家族管理员可邀请家人、调整权限和移除协作者。</view>
<view class="el-h3 tools-section-title">家族协作者</view>
<view v-for="membership in memberships" :key="membership.id" class="tools-record tools-heading"><view><NativeText class="el-strong">{{membership.username||'账号 '+membership.user_id}}</NativeText><view class="form-hint">{{roleLabel(membership.role)}}</view></view><view v-if="isOwner&&membership.role!=='OWNER'" class="tools-actions"><NativeButton class="btn btn-secondary btn-small" :disabled="busy" @click="changeRole(membership)">改为{{membership.role==='EDITOR'?'只读':'可编辑'}}</NativeButton><NativeButton class="btn btn-danger btn-small" :disabled="busy" @click="removeMembership(membership)">移除</NativeButton></view></view>
<view v-if="isOwner" class="el-h3 tools-section-title">发出的邀请</view><view v-if="isOwner&&!outgoing.length" class="tools-empty">暂无邀请记录</view>
<view v-for="invite in outgoing" :key="invite.id" class="tools-record tools-heading"><view><NativeText class="el-strong">{{invite.invitee}} · {{roleLabel(invite.role)}}</NativeText><view class="form-hint">{{inviteStatus(invite.status)}}</view></view><NativeButton v-if="invite.status==='PENDING'||invite.status==='pending'" class="btn btn-secondary btn-small" :disabled="busy" @click="revokeInvite(invite)">撤销</NativeButton></view>
</template>
<template v-else-if="tab==='backup'">
<view class="form-hint">导出包含家族名称、头像图片、全部成员、关系及提醒的 JSON 文件。导入会先经过服务端校验，失败不会替换当前资料。</view>
<view class="tools-actions"><NativeButton class="btn btn-secondary" :disabled="busy" @click="exportData">导出家谱</NativeButton><NativeButton class="btn btn-primary" :disabled="busy||!editable" @click="importData">选择文件并导入</NativeButton><NativeButton v-if="store.importRecoveryAvailable" class="btn btn-secondary" :disabled="busy||!editable" @click="restoreImport">恢复导入前资料</NativeButton></view>
<view v-if="exportPath" class="form-hint">文件已保存：{{exportPath}}</view>
<view class="el-label"><NativeText>备份 JSON 文本（适用于无法选择文件的平台）</NativeText><NativeField class="el-textarea" kind="textarea" rows="6" maxlength="15000000" v-model="backupText" :disabled="busy" placeholder="将导出的完整 JSON 粘贴至此"/></view>
<view class="tools-actions"><NativeButton class="btn btn-secondary" :disabled="busy||!backupText" @click="copyBackup">复制备份文本</NativeButton><NativeButton class="btn btn-primary" :disabled="busy||!editable||!backupText" @click="importBackupText">导入此文本</NativeButton></view>
<view class="el-h3 tools-section-title">迁移旧本机账号资料</view>
<view class="form-hint">仅在保存旧账号的原设备有效。验证旧账号密码后，将其资料迁入当前云端家族并替换当前资料。旧本机账号及缓存会保留，此操作不会创建服务端账号。</view>
<view class="form-grid"><view class="el-label"><NativeText>旧本机登录名</NativeText><NativeField class="el-input" v-model="legacyForm.username" :disabled="busy" maxlength="32" placeholder="旧版本使用的登录名" autocomplete="off"/></view><view class="el-label"><NativeText>旧本机密码</NativeText><NativeField class="el-input" type="password" v-model="legacyForm.password" :disabled="busy" maxlength="64" placeholder="仅用于验证原设备中的旧账号" autocomplete="off"/></view></view>
<NativeButton class="btn btn-secondary" :disabled="busy||!editable" @click="migrateLegacy">验证并迁移旧本机资料</NativeButton>
</template>
<template v-else-if="tab==='audit'">
<view class="form-hint">当前家族最近 100 条服务端操作记录。</view><view v-if="!audit.length" class="tools-empty">暂无记录</view><view v-for="item in audit" :key="item.id" class="tools-record"><NativeText class="el-strong">{{actionLabel(item.action)}} · {{targetLabel(item.target_type)}}</NativeText><view class="form-hint">{{formatTime(item.created_at)}}{{item.target_id?' · 对象 '+item.target_id:''}}</view></view>
</template>
<template v-else-if="tab==='delete'">
<view class="tools-error">注销账号会永久删除账号、本人拥有的家族资料及关联资产，解除参与的家族权限。请先导出需要保留的家谱。</view>
<view class="el-label"><NativeText>输入“注销账号”确认</NativeText><NativeField class="el-input" v-model="deleteConfirmation" :disabled="busy" placeholder="注销账号"/></view>
<NativeButton class="btn btn-danger" :disabled="busy||deleteConfirmation!=='注销账号'" @click="deleteAccount">永久注销账号</NativeButton>
</template>
<view class="dialog-actions"><NativeButton v-if="!store.guest" class="btn btn-secondary" :disabled="busy||loading" @click="loadTab">刷新</NativeButton><NativeButton class="btn btn-secondary" :disabled="busy" @click="$emit('close')">关闭</NativeButton></view>
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
import {computed,reactive,ref,watch,onUnmounted} from 'vue'
import {store,authenticatedRequest,switchFamily,refreshFamily,exportFamilyData,importFamilyData,importLegacyLocalAccount,restorePreviousImport,logout} from '../../utils/store.js'
import {sendSms} from '../../utils/auth.js'
import {chooseJsonFile,downloadJson} from '../../utils/files.js'
import {refreshNotifications,requestSystemNotificationPermission} from '../../utils/notifications.js'
const props=defineProps({initialTab:{type:String,default:'notifications'}}),emit=defineEmits(['close','signed-out'])
const tabs=[{id:'notifications',label:'通知'},{id:'privacy',label:'隐私授权'},{id:'phone',label:'手机号'},{id:'sessions',label:'登录设备'},{id:'families',label:'家族切换'},{id:'collaboration',label:'邀请与权限'},{id:'backup',label:'导入导出'},{id:'audit',label:'操作日志'},{id:'delete',label:'注销账号'}],guestTabs=[{id:'guide',label:'使用说明'}]
const visibleTabs=computed(()=>store.guest?guestTabs:tabs)
const tab=ref(store.guest?'guide':props.initialTab),busy=ref(false),loading=ref(false),error=ref(''),message=ref(''),sessions=ref([]),families=ref([]),incoming=ref([]),outgoing=ref([]),memberships=ref([]),audit=ref([]),deliveryStatus=ref({}),deleteConfirmation=ref(''),backupText=ref(''),exportPath=ref(''),permissionMessage=ref('')
const legacyForm=reactive({username:'',password:''})
const preferences=reactive({notifications_enabled:true,system_notifications_enabled:false}),phoneForm=reactive({phone:'',smsCode:''}),invitation=reactive({invitee:'',role:'EDITOR'})
const notifications=computed(()=>store.notifications||[]),unread=computed(()=>notifications.value.filter(n=>!n.read_at).length),isOwner=computed(()=>store.role==='OWNER'),editable=computed(()=>!store.guest&&store.role!=='VIEWER')
defineExpose({busy})
const roleOptions=[{value:'EDITOR',label:'可编辑成员与纪念日'},{value:'VIEWER',label:'只读'}]
const roleLabel=role=>({OWNER:'管理员',EDITOR:'可编辑',VIEWER:'只读'})[role]||role||'未确认'
const inviteStatus=value=>({PENDING:'待接受',ACCEPTED:'已接受',REJECTED:'已拒绝',REVOKED:'已撤销',EXPIRED:'已过期'})[String(value).toUpperCase()]||value
const formatTime=value=>value?new Date(/Z$|[+-]\d{2}:?\d{2}$/.test(value)?value:value+'Z').toLocaleString('zh-CN'):'时间未记录'
const channelLabel=value=>({in_app:'站内通知',system:'系统通知',push:'后台推送',browser:'浏览器通知',web_push:'浏览器后台推送',native_push:'App 后台推送',mobile_push:'App 后台推送',wechat_push:'微信订阅消息',timezone:'通知时区',scheduler:'服务端定时任务',browser_foreground:'浏览器前台通知',native_local:'App 本机通知'})[value]||value
const statusText=value=>typeof value==='string'?value:typeof value==='boolean'?(value?'可用':'未启用'):value?.message||value?.reason||value?.status||JSON.stringify(value)
const actionLabel=value=>({'family.sync':'同步家谱','family.import':'导入家谱','family.export':'导出家谱','family.select':'切换家族','family.select_personal':'返回自己的家谱','invite_code.create':'生成家族邀请码','invite_code.cancel':'撤销家族邀请码','invite_code.join':'邀请码加入家谱','member.create':'新增成员','member.update':'修改成员','member.delete':'删除成员','member.relationships':'修改亲属关系','reminder.create':'新增提醒','reminder.update':'修改提醒','reminder.delete':'删除提醒','invitation.create':'邀请家人','invitation.accept':'接受邀请','invitation.reject':'拒绝邀请','invitation.cancel':'撤销邀请','membership.role':'修改权限','membership.remove':'移除协作者',sync_updated:'保存家谱',family_sync:'同步家谱',family_import:'导入家谱',family_export:'导出家谱',member_created:'新增成员',member_updated:'修改成员',member_deleted:'删除成员',reminder_created:'新增提醒',reminder_updated:'修改提醒',reminder_deleted:'删除提醒',invitation_created:'邀请家人',invitation_accepted:'接受邀请',invitation_rejected:'拒绝邀请',invitation_revoked:'撤销邀请',membership_updated:'修改权限',membership_removed:'移除协作者',preferences_updated:'修改授权',phone_bound:'绑定手机号',password_reset:'重置密码',account_asset_removed:'移除账号头像',login:'登录',logout:'退出登录',session_logout:'退出登录',session_revoked:'撤销会话'})[value]||value
const targetLabel=value=>({family:'家族',member:'成员',reminder:'提醒',invitation:'邀请',invite_code:'家族邀请码',membership:'协作者',account:'账号',session:'登录设备',asset:'图片'})[value]||value||'家族'
const confirm=async(title,content)=>{const identity=[store.session?.accountId,store.familyId,store.session?.accessToken].join('|');const result=await new Promise(resolve=>uni.showModal({title,content,confirmText:'确认',success:r=>resolve(!!r.confirm),fail:()=>resolve(false)}));if(identity!==[store.session?.accountId,store.familyId,store.session?.accessToken].join('|'))throw Error('账号或家族已切换，请重新操作');return result}
const confirmAction=(title,content)=>confirm(title,content).catch(e=>{error.value=e.message;return false})
let generation=0
async function loadTab(){
  if(store.guest){loading.value=false;error.value='';return}
  const requestGeneration=++generation,account=store.session?.accountId,family=store.familyId,token=store.session?.accessToken
  const stillCurrent=()=>requestGeneration===generation&&account===store.session?.accountId&&family===store.familyId&&token===store.session?.accessToken
  loading.value=true;error.value=''
  const apply=fn=>value=>{if(stillCurrent())fn(value)}
  try{
    if(tab.value==='notifications')await refreshNotifications()
    if(tab.value==='privacy')await Promise.all([authenticatedRequest('/auth/me').then(apply(user=>{store.user=user;Object.assign(preferences,user)})),authenticatedRequest('/notifications/delivery-status').then(apply(value=>deliveryStatus.value=value))])
    if(tab.value==='phone')await authenticatedRequest('/auth/me').then(apply(user=>store.user=user))
    if(tab.value==='sessions')await authenticatedRequest('/auth/sessions').then(apply(value=>sessions.value=value))
    if(tab.value==='families')await Promise.all([authenticatedRequest('/family/list').then(apply(value=>families.value=value)),authenticatedRequest('/family/invitations/incoming').then(apply(value=>incoming.value=value))])
    if(tab.value==='collaboration')await Promise.all([authenticatedRequest('/family/memberships').then(apply(value=>memberships.value=value)),...(isOwner.value?[authenticatedRequest('/family/invitations').then(apply(value=>outgoing.value=value))]:[])])
    if(tab.value==='audit')await authenticatedRequest('/family/audit').then(apply(value=>audit.value=value))
  }catch(e){if(stillCurrent())error.value=e.message}finally{if(stillCurrent())loading.value=false}
}
async function run(action,successMessage='已保存'){if(busy.value)return;busy.value=true;error.value='';message.value='';const account=store.session?.accountId,token=store.session?.accessToken,family=store.familyId;const assertCurrent=()=>{if(account!==store.session?.accountId||token!==store.session?.accessToken||family!==store.familyId)throw Error('账号或家族已切换，请重新操作')};try{await action(assertCurrent);if(account===store.session?.accountId&&token===store.session?.accessToken){message.value=successMessage;await loadTab()}}catch(e){if(account===store.session?.accountId&&token===store.session?.accessToken)error.value=e.message}finally{busy.value=false}}
function markRead(notice){return run(async()=>{await authenticatedRequest(`/notifications/${notice.id}/read`,{method:'PATCH'});await refreshNotifications()},'已标记为已读')}
function markAllRead(){return run(async()=>{await authenticatedRequest('/notifications/read-all',{method:'POST'});await refreshNotifications()},'全部通知已读')}
function savePreferences(){return run(async()=>{const identity=[store.session?.accountId,store.session?.accessToken,store.familyId].join('|');const user=await authenticatedRequest('/auth/preferences',{method:'PATCH',data:{notifications_enabled:!!preferences.notifications_enabled,system_notifications_enabled:!!preferences.system_notifications_enabled}});if(identity===[store.session?.accountId,store.session?.accessToken,store.familyId].join('|'))store.user=user},'授权设置已保存到服务器')}
function requestPermission(){return run(async()=>{const result=await requestSystemNotificationPermission();if(result===false||result?.granted===false||result?.supported===false)throw Error(result?.message||'当前设备未授予通知权限，请检查系统设置。');if(result?.message)permissionMessage.value=result.message},'设备通知权限请求已完成')}
const smsCountdown=ref(0),smsEnds=new Map();let smsTimer
function updateSmsCountdown(){const end=smsEnds.get(phoneForm.phone.trim())||0;smsCountdown.value=Math.max(0,Math.ceil((end-Date.now())/1000))}
function sendPhoneCode(){return run(async()=>{const phone=phoneForm.phone.trim();await sendSms(phone,store.user?.phone?'modify_phone':'bind_phone');smsEnds.set(phone,Date.now()+60000);updateSmsCountdown();if(!smsTimer)smsTimer=setInterval(updateSmsCountdown,1000)},'短信验证码已发送')}
function bindPhone(){return run(async()=>{const identity=[store.session?.accountId,store.session?.accessToken,store.familyId].join('|');const user=await authenticatedRequest('/auth/bind-phone',{method:'POST',data:{phone:phoneForm.phone.trim().normalize('NFKC'),sms_code:phoneForm.smsCode.trim().normalize('NFKC'),scene:store.user?.phone?'modify_phone':'bind_phone'}});if(identity===[store.session?.accountId,store.session?.accessToken,store.familyId].join('|')){store.user=user;phoneForm.smsCode=''}},'手机号已保存到服务器')}
async function revokeSession(session){if(!await confirmAction('撤销登录设备',session.current?'撤销当前会话后将退出登录，确认继续？':'确认撤销此会话？该设备将无法继续访问账号。'))return;return run(async()=>{await authenticatedRequest(`/auth/sessions/${session.id}`,{method:'DELETE'});if(session.current){await logout();emit('signed-out')}},'会话已撤销')}
function activateFamily(family){return run(async()=>{await switchFamily(family.id)},'已切换家族')}
function respondInvite(invite,accept){return run(async()=>{if(String(invite.status).toUpperCase()!=='PENDING')throw Error('该邀请已处理或已过期。');if(accept&&['pending','saving','conflict','error'].includes(store.syncStatus))throw Error('请先同步当前家族的修改，再接受邀请。');const result=await authenticatedRequest(`/family/invitations/${invite.id}/${accept?'accept':'reject'}`,{method:'POST'});if(accept){store.user={...store.user,active_family_id:Number(result.family_id)};store.session.user=store.user;await switchFamily(invite.family_id)}},accept?'已接受邀请并进入家族':'已拒绝邀请')}
function inviteMember(){return run(async()=>{if(!invitation.invitee.trim())throw Error('请填写对方登录名或手机号');await authenticatedRequest('/family/invitations',{method:'POST',data:{invitee:invitation.invitee.trim(),role:invitation.role}});invitation.invitee=''},'站内邀请已保存，对方可在“家族切换”查看')}
async function revokeInvite(invite){if(!await confirmAction('撤销邀请',`确认撤销发给 ${invite.invitee} 的邀请？`))return;return run(()=>authenticatedRequest(`/family/invitations/${invite.id}`,{method:'DELETE'}),'邀请已撤销')}
async function changeRole(member){const role=member.role==='EDITOR'?'VIEWER':'EDITOR';if(!await confirmAction('修改权限',`将 ${member.username||member.user_id} 改为${roleLabel(role)}，确认继续？`))return;return run(async()=>{await authenticatedRequest(`/family/memberships/${member.id}`,{method:'PATCH',data:{role}});await refreshFamily()},'权限已更新')}
async function removeMembership(member){if(!await confirmAction('移除协作者',`确认移除 ${member.username||member.user_id}？对方将无法访问此家族。`))return;return run(async()=>{await authenticatedRequest(`/family/memberships/${member.id}`,{method:'DELETE'});await refreshFamily()},'已移除协作者')}
function exportData(){return run(async assertCurrent=>{const data=await exportFamilyData();assertCurrent();const result=await downloadJson(data);backupText.value=result?.content||JSON.stringify(data,null,2);exportPath.value=result?.path||'';if(result?.downloaded===false)throw Error('当前平台未生成文件，备份文本已显示，可复制保存。')},'家谱文件已导出')}
async function importData(){return run(async assertCurrent=>{const file=await chooseJsonFile();assertCurrent();if(!file)throw Error('已取消文件选择');const data=typeof file==='string'?JSON.parse(file):file.data||file;if(!await confirmAction('导入并替换当前家谱',`将覆盖“${store.profile.name}”的成员、关系与纪念日，确认继续？`))throw Error('已取消导入');assertCurrent();const result=await importFamilyData(data);if(result?.synced===false)throw Error('导入已保存到本机，等待同步，请查看同步状态')},'家谱已导入并同步')}
function copyBackup(){uni.setClipboardData({data:backupText.value,success:()=>message.value='备份文本已复制',fail:()=>error.value='复制失败，请手动选择并复制备份文本。'})}
async function importBackupText(){return run(async assertCurrent=>{let data;try{data=JSON.parse(backupText.value)}catch{throw Error('备份文本不是有效 JSON。')}if(!await confirmAction('导入并替换当前家谱',`确认用备份文本替换“${store.profile.name}”？`))throw Error('已取消导入');assertCurrent();const result=await importFamilyData(data);if(result?.synced===false)throw Error('导入已保存到本机，等待同步，请查看同步状态')},'家谱已导入并同步')}
async function restoreImport(){return run(async assertCurrent=>{if(!await confirmAction('恢复导入前资料','将恢复最近一次导入前的本机资料，确认继续？'))throw Error('已取消恢复');assertCurrent();const result=await restorePreviousImport();if(result?.synced===false)throw Error('恢复资料已保存到本机，等待同步，请查看同步状态')},'已恢复导入前资料')}
async function migrateLegacy(){return run(async assertCurrent=>{if(!legacyForm.username.trim()||!legacyForm.password)throw Error('请填写旧本机账号与密码。');if(!await confirmAction('迁移旧本机资料',`验证后将替换“${store.profile.name}”的家谱资料，确认继续？`))throw Error('已取消迁移');assertCurrent();let result;try{result=await importLegacyLocalAccount(legacyForm.username.trim(),legacyForm.password)}finally{legacyForm.password=''}if(result?.synced===false)throw Error('旧资料已保存到本机，等待同步，请查看同步状态')},'旧本机资料已迁入当前家族')}
async function deleteAccount(){if(deleteConfirmation.value!=='注销账号'||!await confirmAction('永久注销账号','此操作无法恢复。确认删除账号及本人拥有的家族资料？'))return;return run(async()=>{await authenticatedRequest('/auth/me',{method:'DELETE'});await logout();emit('signed-out')},'账号已注销')}
watch(tab,()=>{message.value='';loadTab()},{immediate:true});watch(()=>props.initialTab,value=>{tab.value=store.guest?'guide':value});watch(()=>store.guest,value=>{tab.value=value?'guide':props.initialTab});watch(()=>[store.session?.accountId,store.familyId,store.session?.accessToken],()=>{generation++});watch(()=>phoneForm.phone,updateSmsCountdown)
onUnmounted(()=>{generation++;clearInterval(smsTimer)})
</script>
<style>
.tools-dialog { width:min(860px,calc(100vw - 32px)); max-height:min(760px,calc(100vh - 32px)); overflow:auto; padding:32px 34px 24px; border:1px solid rgba(139,47,42,.18); border-radius:18px; background:linear-gradient(145deg,#fffdf9 0%,#f7f2ea 100%); box-shadow:0 28px 80px rgba(58,35,28,.24),0 2px 0 rgba(255,255,255,.8) inset; }
.tools-dialog .dialog-header { margin-bottom:24px; align-items:center; }
.tools-dialog .dialog-header .eyebrow { color:#a05b48; letter-spacing:.24em; font-size:10px; }
.tools-dialog .dialog-header .el-h2 { font-size:32px; letter-spacing:.04em; color:#312722; }
.tools-dialog .icon-btn { width:38px; height:38px; border-radius:10px; background:rgba(255,255,255,.6); border-color:#d8cbc0; }
.tools-dialog .icon-btn:hover { background:#fff; border-color:var(--brand); }
.tools-tabs { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:7px; margin:0 -2px 24px; padding:0 0 18px; border-bottom:1px solid #ded2c7; }
.tools-tabs > button,.tools-tabs > uni-button { min-height:38px; margin:0; padding:7px 8px; border:1px solid transparent; border-radius:9px; color:#796d64; background:transparent; font:600 12px/1.3 'PingFang SC',sans-serif; transition:all .16s ease; }
.tools-tabs > button:hover,.tools-tabs > uni-button:hover { background:#f1e9e0; color:#603b32; }
.tools-tabs > button.active,.tools-tabs > uni-button.active { color:#fffaf5; border-color:#8b2f2a; background:#8b2f2a; box-shadow:0 5px 12px rgba(139,47,42,.2); }
.tools-dialog .form-hint { color:#887a70; font-size:12px; }
.tools-dialog .el-label { color:#54463e; font-size:13px; font-weight:600; }
.tools-dialog .el-input,.tools-dialog .el-select,.tools-dialog .el-textarea { min-height:46px; border:1px solid #d8cbc0; border-radius:10px; background:rgba(255,255,255,.78); color:#312722; padding:11px 13px; font-size:14px; transition:border-color .16s ease,box-shadow .16s ease; }
.tools-dialog .el-input:focus,.tools-dialog .el-select:focus,.tools-dialog .el-textarea:focus { border-color:#a05b48; box-shadow:0 0 0 3px rgba(160,91,72,.13); outline:0; }
.tools-dialog .btn { min-height:42px; border-radius:10px; font-size:13px; }
.tools-dialog .btn-primary { background:#8b2f2a; box-shadow:0 5px 12px rgba(139,47,42,.16); }
.tools-dialog .btn-secondary { border-color:#d8cbc0; background:#fffdf9; }
.tools-dialog .tools-record { margin:10px 0; border:1px solid #e0d5cb; border-radius:12px; background:rgba(255,255,255,.65); padding:15px 16px; }
.tools-dialog .tools-record:hover { border-color:#c6a99b; }
.tools-dialog .tools-section-title { color:#3c302a; font-size:16px; letter-spacing:.03em; }
.tools-dialog .dialog-actions { margin-top:26px; padding-top:18px; border-top:1px solid #ded2c7; }
.tools-error,.tools-message { padding:10px 12px; margin:12px 0; font-size:12px; line-height:1.7; }
.tools-error { color:var(--brand); border:1px solid rgba(139,47,42,.25); background:#fff6f4; }
.tools-message { background:#f0f3eb; color:#4a6641; }
.tools-heading,.tools-actions { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }
.tools-actions { justify-content:flex-start; margin:12px 0; }
.tools-record { display:block; width:100%; margin:10px 0; border:1px solid var(--line); background:#fffdf8; padding:14px; text-align:left; color:var(--ink); font-size:13px; line-height:1.65; }
.tools-record.tools-heading { display:flex; }
.tools-record .el-strong { font-weight:600; }
.tools-record .el-small { font-size:11px; color:var(--muted); }
.tools-record .el-p { margin:5px 0; }
.notice-unread { border-left:3px solid var(--brand); }
.tools-empty { padding:22px 0; color:var(--muted); font-size:13px; }
.tools-switch { display:flex; align-items:flex-start; gap:14px; margin:20px 0; }
.tools-section-title { margin:24px 0 10px; }
.guest-guide-intro,.guest-login-note { display:flex; align-items:flex-start; gap:12px; padding:14px 0; }
.guest-guide-icon { color:var(--brand); font-size:24px; margin-top:2px; }
.guest-guide-list { display:grid; gap:10px; }
.guest-guide-list>view { display:flex; align-items:flex-start; gap:12px; padding:12px 0; border-top:1px solid var(--line); }
.guest-guide-list>view>.ph,.guest-login-note>.ph { color:var(--brand); font-size:19px; margin-top:2px; }
.guest-guide-list .el-strong,.guest-guide-list .form-hint { display:block; }
.guest-login-note { margin-top:20px; border-top:1px solid var(--line); }
@media(max-width:700px){.tools-dialog{width:calc(100vw - 20px);max-height:calc(100dvh - 20px);padding:24px 18px 18px;border-radius:16px}.tools-dialog .dialog-header .el-h2{font-size:27px}.tools-tabs{grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:20px}.tools-tabs > button,.tools-tabs > uni-button{min-height:36px;font-size:11px}.tools-actions .btn{min-height:38px;flex:1}.tools-dialog .dialog-actions .btn{flex:0 0 auto}}
</style>
