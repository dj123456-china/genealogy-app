import {ref, reactive, computed, nextTick, onUnmounted, watch, onMounted} from 'vue'
import {onBackPress, onResize, onShow, onLoad} from '@dcloudio/uni-app'
import {store,activateSession,enterGuest,logout,saveParityMember,deleteMember,saveReminder,deleteReminder,saveProfile,clearCurrentData,retrySync,resolveSyncConflict,discardPendingChanges,exportFamilyData} from './store.js'
import {useLoginForm} from './login-form.js'
import {createFamilyGuideFlow} from './family-guide.js'
import {readStorage,writeStorage} from './storage.js'
import {dateString,parseDate,qingmingDate} from './dates.js'
import {generationFor,genderFor,RELATIONS,parentLinks,parentFields,formParentLinks} from './family.js'
import {persistAvatar,resolveAvatar} from './avatar.js'
import {downloadJson} from './files.js'
import {refreshNotifications} from './notifications.js'
import {demoMembers,reminderViews,displayGeneration,lunarInfo,calendarDays,inferRelationshipByYears,analyzeNames,memberLabel} from './parity-domain.js'
export function useParityPage(){
  const pageTitles={home:'家族首页',genealogy:'家族谱',reminders:'纪念日',account:'我的账户'}
  const currentPage=ref('home'),dialog=ref(store.session||store.sessionRestoring?'':'loginDialog'),treeView=ref('tree'),search=ref(''),userTree=ref(null),demoTree=ref(null),accountTools=ref(null),familySharing=ref(null)
  const theme=ref(readStorage('family-theme','light') === 'dark' ? 'dark' : 'light')
  function setTheme(value){theme.value=value==='dark'?'dark':'light';writeStorage('family-theme',theme.value)}
  const elderMode=ref(readStorage('family-elder-mode',false) === true)
  function setElderMode(value){elderMode.value=!!value;writeStorage('family-elder-mode',elderMode.value)}
  const legalDocument=ref('disclaimer')
  let legalReturnDialog=''
  function openLegal(document){if(!['disclaimer','rules'].includes(document))return;if(dialog.value!=='legalDialog')legalReturnDialog=dialog.value;legalDocument.value=document;dialog.value='legalDialog'}
  function closeLegal(){if(dialog.value!=='legalDialog')return;dialog.value=legalReturnDialog;legalReturnDialog=''}
  const familyGuides=createFamilyGuideFlow({dialog,currentPage,notify:message=>toast(message),onNavigate:action=>nextTick(()=>familySharing.value?.navigate(action))})
  let guidedSession='',manualLogin=false
  const today=ref(new Date()),todayLabel=computed(()=>{const d=today.value;return `${d.getFullYear()}年${d.getMonth()+1}月${d.getDate()}日星期${'日一二三四五六'[d.getDay()]}`})
  const saveBusy=ref(false),avatarBusy=ref(false),canEdit=computed(()=>!!store.session&&!store.guest&&store.role!=='VIEWER'&&!['loading','saving'].includes(store.syncStatus))
  const contextIdentity=()=>[store.session?.accountId,store.familyId,store.session?.accessToken].join('|')
  let formIdentity='',personIdentity=''
  function assertFormContext(){if(!formIdentity||formIdentity!==contextIdentity())throw Error('账号或家族已切换，请重新打开表单操作。')}
  watch(dialog,id=>{store.editing=['memberDialogForm','reminderDialog','profileDialog'].includes(id)},{immediate:true,flush:'sync'})
  onUnmounted(()=>{store.editing=false})
  const toolsTab=ref('notifications'),pendingNotificationEntry=ref(false)
  const requestNotificationEntry=()=>pendingNotificationEntry.value=true
  onLoad(query=>{if(String(query?.notifications)==='1')requestNotificationEntry()})
  uni.$on('family-open-notifications',requestNotificationEntry)
  onUnmounted(()=>uni.$off('family-open-notifications',requestNotificationEntry))
  const notificationEntryReady=()=>pendingNotificationEntry.value&&store.session&&!store.guest&&store.sessionValidated&&!dialog.value&&!familyGuides.familyGuideBusy.value&&!familyGuides.familyGuidePending.value
  watch(()=>[pendingNotificationEntry.value,dialog.value,store.session?.accountId,store.sessionValidated,familyGuides.familyGuideBusy.value,familyGuides.familyGuidePending.value],()=>{if(notificationEntryReady())nextTick(()=>{if(!notificationEntryReady())return;pendingNotificationEntry.value=false;openTools('notifications')})})
  function openTools(tab='notifications'){if(!store.session){toast('请登录后使用账户和通知功能','ph-lock-key');return};if(['families','collaboration'].includes(tab)){currentPage.value='account';nextTick(()=>familySharing.value?.navigate(tab==='collaboration'?'invite':'join'));return};toolsTab.value=tab;dialog.value='accountTools'}
  const unreadNotifications=computed(()=>(store.notifications||[]).filter(n=>!n.read_at).length)
  const syncLabel=computed(()=>({local:'旧本机账号，资料尚未上传',idle:'尚未同步',loading:'正在读取云端资料',saving:'正在保存到云端',synced:'已同步到云端',pending:'已保存到本机，等待同步',conflict:'本机与云端存在修改冲突',error:'云端同步失败'})[store.syncStatus]||'本机资料')
  const conflictDetails=computed(()=>{const conflicts=store.conflicts||[],snapshots=store.syncConflict||{};const labels={name:'名称',avatar:'头像',relation:'与本人的关系',gender:'性别',generation:'世代',birthday:'出生日期',deathYear:'卒年',deathDate:'忌日',parentIds:'父母关联',parentRoles:'父母角色',spouseId:'配偶',avatarLabel:'头像文字',avatarName:'头像说明',bio:'生平',title:'提醒名称',date:'日期',type:'提醒类型',advance:'提前提醒',repeat:'重复',calendar_type:'历法'};return conflicts.map(path=>{const match=/^(members|reminders):([^\.]+)(?:\.(.+))?$/.exec(path);const value=snapshot=>{if(!snapshot)return undefined;if(match){const entity=snapshot[match[1]]?.find(e=>String(e.id)===match[2]);if(entity&&match[1]==='members'&&match[3]==='parentIds')return parentLinks(entity,snapshot.members).map(link=>`${({father:'父亲',mother:'母亲',parent:'父母'})[link.role]}：${memberLabel(snapshot.members.find(m=>m.id===link.id),snapshot.members)}`).join('；')||'未指定';return match[3]?match[3].split('.').reduce((v,k)=>v?.[k],entity):entity}return path.split('.').reduce((v,k)=>v?.[k],snapshot)};const local=value(snapshots.local),remote=value(snapshots.remote),entity=match?(snapshots.local?.[match[1]]?.find(e=>String(e.id)===match[2])||snapshots.remote?.[match[1]]?.find(e=>String(e.id)===match[2])):null;const title=match?`${match[1]==='members'?'成员':'提醒'} ${entity?.name||entity?.title||match[2]}${match[3]?' · '+(labels[match[3]]||match[3]):''}`:`家族${labels[path.split('.')[1]]||'资料'}`;const describe=v=>v===undefined?'已删除':typeof v==='string'?v:JSON.stringify(v);return `${title}\n本机：${describe(local)}\n云端：${describe(remote)}`}).join('\n\n')})
  async function syncNow(){try{await retrySync()}catch(e){toast(e.message,'ph-warning-circle')}}
  async function resolveConflict(choice){const ok=await confirmAction('处理同步冲突',choice==='local'?'保留本机的冲突修改，并将已合并资料保存到云端，确认继续？':'采用云端资料，本机尚未同步的修改将被替换，确认继续？');if(!ok)return;try{await resolveSyncConflict(choice)}catch(e){toast(e.message,'ph-warning-circle')}}
  const dayTimer=setInterval(()=>{const d=new Date();if(dateString(d)!==dateString(today.value))today.value=d},30000)
  onShow(()=>{today.value=new Date()})
  onMounted(()=>{if(store.session&&!store.guest)refreshNotifications().catch(()=>{})})
  onUnmounted(()=>{clearInterval(dayTimer)})
  const confirm=async(title,content)=>{const identity=[store.session?.accountId,store.familyId,store.session?.accessToken].join('|');const result=await new Promise(resolve=>uni.showModal({title,content,confirmText:'确认',success:r=>resolve(!!r.confirm),fail:()=>resolve(false)}));if(identity!==[store.session?.accountId,store.familyId,store.session?.accessToken].join('|'))throw Error('账号或家族已切换，请重新操作');return result}
  const confirmAction=(title,content)=>confirm(title,content).catch(e=>{toast(e.message,'ph-warning-circle');return false})
  function assertEditable(){if(!canEdit.value)throw Error(store.role==='VIEWER'?'当前家族为只读权限，请联系管理员。':'请先登录后修改家谱。')}
  const savedMessage=result=>result?.synced?'已同步到云端':'已保存到本机，等待同步'
  const generationCount=computed(()=>new Set(store.members.map(displayGeneration)).size)
  const toastState=reactive({show:false,message:'',icon:'ph-check-circle'});let timer
  function toast(message,icon='ph-check-circle'){clearTimeout(timer);Object.assign(toastState,{show:true,message,icon});timer=setTimeout(()=>toastState.show=false,2800)}
  onUnmounted(()=>{clearTimeout(timer)})
  const selectedNames=ref([]),selecting=ref(false)
  const selectedMemberNames=computed(()=>selectedNames.value.map(id=>store.members.find(m=>m.id===id)?.name||'')),selectedLabels=computed(()=>selectedNames.value.map(id=>memberLabel(store.members.find(m=>m.id===id),store.members)))
  const selectionNote=computed(()=>selecting.value?(selectedNames.value.length?`已选择 ${selectedLabels.value[0]}，请再点击一位成员`:'请依次点击两位成员图标'):'点击“选择两人”，再依次点击两个成员图标分析关系')
  function scrollMain(){uni.pageScrollTo({scrollTop:0,duration:0})}
  function clearSelection(){selecting.value=false;selectedNames.value=[]}
  async function center(){await nextTick();await (treeView.value==='demo'?demoTree.value:userTree.value)?.center()}
  function setTreeView(view){treeView.value=view;clearSelection();if(view==='demo'&&store.session)writeStorage('family-demo-seen-v1:'+store.session.accountId,'seen');center()}
  function showPage(page){if(!store.session){dialog.value='loginDialog';return}const entering=page==='genealogy'&&currentPage.value!==page;currentPage.value=pageTitles[page]?page:'home';if(page!=='genealogy')clearSelection();scrollMain();if(entering)setTreeView('tree')}
  onResize(()=>{if(currentPage.value==='genealogy')center()})
  function resetTree(){search.value='';center();toast(treeView.value==='demo'?'示范族谱已居中':'家族谱已居中','ph-crosshair')}
  const filteredMembers=computed(()=>store.members.filter(m=>`${m.name}${m.relation}${m.avatarName||''}`.toLowerCase().includes(search.value.trim().toLowerCase())))
  const memberNames=computed(()=>store.members.map(m=>m.name)),relationMemberOptions=computed(()=>[{value:'',label:'请选择具体成员'},...store.members.map(m=>({value:m.id,label:memberLabel(m,store.members)}))]),activeMember=ref(null),editingId=ref('')
  const emptyMember=()=>({name:'',relation:'',gender:'未知',generation:3,birthday:'',deathYear:'',deathDate:'',parentOne:'',parentTwo:'',spouseId:'',avatarLabel:'',avatarName:'',bio:'',deceased:false,createBirthdayReminder:false,createMemorialReminder:false})
  const memberForm=reactive(emptyMember()),memberLunar=computed(()=>lunarInfo(memberForm.birthday).full)
  const emptyReminder=()=>({id:'',title:'',type:'birthday',memberId:'',date:'',advance:'当天',repeat:'每年',calendar_type:'solar'})
  const reminderForm=reactive(emptyReminder()),reminderLunar=computed(()=>lunarInfo(reminderForm.date).short)
  const reminderMemberOptions=computed(()=>[{value:'',label:'请选择相关人员（可选）'},...store.members.map(m=>({value:m.id,label:memberLabel(m,store.members)}))])
  const relationOptions=[{value:'',label:'请选择'},...RELATIONS.map(value=>({value,label:value}))]
  const relatedMemberOptions=computed(()=>[{value:'',label:'未指定'},...store.members.filter(m=>m.id!==editingId.value).map(m=>({value:m.id,label:memberLabel(m,store.members)}))])
  const formRelations=computed(()=>[{role:'父亲',id:memberForm.parentOne},{role:'母亲',id:memberForm.parentTwo},{role:'配偶',id:memberForm.spouseId}].filter(link=>link.id).map(link=>({...link,label:memberLabel(store.members.find(m=>m.id===link.id),store.members)})))
  const personRelations=computed(()=>{
    const member=store.members.find(m=>m.id===activeMember.value?.id)||activeMember.value
    if(!member)return []
    const links=parentLinks(member,store.members).map(link=>({id:link.id,role:({father:'父亲',mother:'母亲',parent:'父母'})[link.role]}))
    if(member.spouseId)links.push({id:member.spouseId,role:'配偶'})
    for(const child of store.members.filter(m=>(m.parentIds||[]).includes(member.id)))links.push({id:child.id,role:'子女'})
    return links.map(link=>({...link,member:store.members.find(m=>m.id===link.id)})).filter(link=>link.member).map(link=>({...link,label:memberLabel(link.member,store.members)}))
  })
  function viewRelatedPerson(id){if(personIdentity!==contextIdentity()){toast('账号或家族已切换，请重新选择成员。','ph-warning-circle');return};const member=store.members.find(m=>m.id===id);if(member)pickPerson(member)}
  watch(()=>memberForm.relation,relation=>{
    if(editingId.value)return
    memberForm.generation=generationFor(relation,store.members,[memberForm.parentOne,memberForm.parentTwo].filter(Boolean))
    const gender=genderFor(relation)
    if(gender!=='未知')memberForm.gender=gender
  })
  watch(()=>[memberForm.parentOne,memberForm.parentTwo],parents=>{
    if(!editingId.value&&parents.some(Boolean))memberForm.generation=generationFor(memberForm.relation,store.members,parents.filter(Boolean))
  })
  function openDialog(id){if(!store.session){dialog.value='loginDialog';return}if(!canEdit.value){toast(store.role==='VIEWER'?'当前家族为只读权限，请联系管理员。':'访客模式仅支持浏览，请先登录后再操作','ph-lock-key');return}formIdentity=contextIdentity();if(id==='memberDialogForm'){Object.assign(memberForm,emptyMember());editingId.value='';if(treeView.value==='demo')setTreeView('tree')}if(id==='reminderDialog')Object.assign(reminderForm,emptyReminder());dialog.value=id}
  function closeDialog(){if(dialog.value==='legalDialog'){closeLegal();return};if(saveBusy.value||avatarBusy.value||loginBusy.value||accountTools.value?.busy||familyGuides.familyGuideBusy.value)return;if(dialog.value==='loginDialog'&&!store.session)return;if(dialog.value==='familyGuide'){if(familyGuides.familyGuideMode.value==='invite'){familyGuides.enterPersonalFromLogin();return};familyGuides.closeFamilyGuide();return};if(dialog.value==='relationDialog')clearSelection();dialog.value='';formIdentity='';Object.assign(memberForm,emptyMember());Object.assign(reminderForm,emptyReminder())}
  onBackPress(()=>{if(dialog.value){closeDialog();return true}if(currentPage.value!=='home'){showPage('home');return true}return false})
  // #ifdef H5
  const handleNotificationUrl=()=>{if(/(?:[?&])notifications=1(?:&|$)/.test(window.location.hash+window.location.search))requestNotificationEntry()}
  const handleNotificationMessage=e=>{if(e.data?.type==='family-notification-click')requestNotificationEntry()}
  onMounted(handleNotificationUrl)
  window.addEventListener('hashchange',handleNotificationUrl)
  navigator.serviceWorker?.addEventListener('message',handleNotificationMessage)
  onUnmounted(()=>{window.removeEventListener('hashchange',handleNotificationUrl);navigator.serviceWorker?.removeEventListener('message',handleNotificationMessage)})
  let returnFocus=null
  let lockedScrollY=0
  function lockPageScroll(locked){
    const body=document.body
    if(!body)return
    if(locked){
      lockedScrollY=window.scrollY||window.pageYOffset||0
      body.style.position='fixed'
      body.style.top=`-${lockedScrollY}px`
      body.style.left='0'
      body.style.right='0'
      body.style.width='100%'
      body.style.overflow='hidden'
    }else{
      body.style.position=''
      body.style.top=''
      body.style.left=''
      body.style.right=''
      body.style.width=''
      body.style.overflow=''
      window.scrollTo(0,lockedScrollY)
    }
  }
  const handleEscape=e=>{
    if(!dialog.value)return
    if(e.key==='Escape'){e.preventDefault();closeDialog()}
    if(e.key==='Tab'){
      const items=Array.from(document.querySelectorAll('.modal-layer button:not([disabled]), .modal-layer input:not([disabled]), .modal-layer select:not([disabled]), .modal-layer textarea:not([disabled]), .modal-layer [tabindex]:not([tabindex="-1"]):not([disabled])')).filter(e=>e.getClientRects().length)
      const index=items.indexOf(document.activeElement)
      if(e.shiftKey && index<=0){e.preventDefault();items[items.length-1]?.focus()}
      else if(!e.shiftKey && (index<0 || index===items.length-1)){e.preventDefault();items[0]?.focus()}
    }
  }
  watch(dialog,async (id,old)=>{
    if(id&&!old)returnFocus=document.activeElement
    if(id&&!old)lockPageScroll(true)
    if(!id&&old)lockPageScroll(false)
    await nextTick()
    const shell=document.querySelector('.app-shell');if(shell)shell.inert=!!id
    if(id){document.querySelector(id==='loginDialog'?'#loginIdentifier, #loginUsername, #loginPhone':'.modal-layer button')?.focus({preventScroll:true})}
    else returnFocus?.focus?.({preventScroll:true})
  },{immediate:true})
  window.addEventListener('keydown',handleEscape)
  onUnmounted(()=>{window.removeEventListener('keydown',handleEscape);const shell=document.querySelector('.app-shell');if(shell)shell.inert=false;lockPageScroll(false)})
  // #endif
  async function submitMember(){
    if(saveBusy.value)return
    saveBusy.value=true
    try{
      assertFormContext();assertEditable()
      const name=memberForm.name.trim(),birthday=memberForm.birthday,deathDate=memberForm.deathDate
      const deathYearInput=String(memberForm.deathYear||'').trim()
      const deathYear=deathDate?Number(deathDate.slice(0,4)):deathYearInput?Number(deathYearInput):null,birthYear=Number(birthday.slice(0,4))||null
      if(!name||name.length>12)throw Error('请填写 1 至 12 个字的姓名。')
      if(!memberForm.relation)throw Error('请选择与我的关系。')
      if(birthday&&(!parseDate(birthday)||birthday>dateString(today.value)))throw Error('出生日期无效或晚于今天。')
      if(deathDate&&(!parseDate(deathDate)||deathDate>dateString(today.value)||(birthday&&deathDate<birthday)))throw Error('忌日无效，须在出生日期与今天之间。')
      if(deathYearInput&&!/^\d{4}$/.test(deathYearInput))throw Error('卒年须填写四位数字。')
      if(deathYear&&(!Number.isInteger(deathYear)||deathYear<1000||deathYear>today.value.getFullYear()||(birthYear&&deathYear<birthYear)))throw Error('卒年应在出生年份与当前年份之间。')
      const generation=Number(memberForm.generation)
      if(!Number.isInteger(generation)||generation<1||generation>100)throw Error('世代须为 1 至 100 的整数。')
      if(memberForm.createBirthdayReminder&&!birthday)throw Error('创建生日提醒需要填写出生日期。')
      if(memberForm.createMemorialReminder&&!deathDate)throw Error('创建忌日提醒需要填写具体忌日。')
      const old=store.members.find(m=>m.id===editingId.value)
      const raw={...memberForm,name,id:old?.id,birthday,birthYear,deathYear:memberForm.deceased?deathYear:null,deathDate:memberForm.deceased?deathDate:'',deceased:!!memberForm.deceased,...formParentLinks(memberForm),spouseId:memberForm.spouseId||'',lunarBirthday:memberLunar.value,generation,avatarLabel:memberForm.avatarLabel.trim().slice(0,8),avatarName:memberForm.avatarName.trim().slice(0,32),bio:memberForm.bio.trim(),autoBirthday:!!memberForm.createBirthdayReminder,autoMemorial:!!memberForm.createMemorialReminder}
      const result=await saveParityMember(raw)
      assertFormContext()
      writeStorage('family-last-member',raw);saveBusy.value=false;closeDialog();setTreeView('tree');toast(`${name} 的档案${savedMessage(result)}`)
    }catch(e){toast(e.message,'ph-warning-circle')}finally{saveBusy.value=false}
  }
  function pickPerson(member){
    if(selecting.value){
      if(selectedNames.value.includes(member.id)){selectedNames.value=selectedNames.value.filter(n=>n!==member.id);return}
      selectedNames.value.push(member.id)
      if(selectedNames.value.length===1){toast(`已选择 ${member.name}，请再选择一人`,'ph-cursor-click');return}
      dialogResult.value=analyzeNames(store.members,...selectedNames.value);selecting.value=false;dialog.value='relationDialog'
    }else{activeMember.value=member;personIdentity=contextIdentity();dialog.value='personDialog'}
  }
  function editActiveMember(){if(!canEdit.value)return;if(personIdentity!==contextIdentity()){toast('账号或家族已切换，请重新选择成员。','ph-warning-circle');return};const m=store.members.find(m=>m.id===activeMember.value?.id);if(!m){toast('该成员已删除，请重新选择。','ph-warning-circle');return};formIdentity=contextIdentity();Object.assign(memberForm,emptyMember(),m,{...parentFields(m,store.members),createBirthdayReminder:store.reminders.some(r=>r.id===`auto-birthday-${m.id}`),createMemorialReminder:store.reminders.some(r=>r.id===`auto-memorial-${m.id}`)});editingId.value=m.id;dialog.value='memberDialogForm'}
  async function removeActiveMember(){if(!canEdit.value||saveBusy.value)return;if(personIdentity!==contextIdentity()){toast('账号或家族已切换，请重新选择成员。','ph-warning-circle');return};const m=store.members.find(m=>m.id===activeMember.value?.id);if(!m||!await confirmAction('删除成员',`确认删除 ${m.name}？关联关系会解除，自动生日和忌日提醒会删除，手动提醒保留为独立记录。`))return;saveBusy.value=true;try{const result=await deleteMember(m.id);saveBusy.value=false;closeDialog();activeMember.value=null;toast('成员已删除，'+savedMessage(result),'ph-trash')}catch(e){toast(e.message,'ph-warning-circle')}finally{saveBusy.value=false}}
  function remindActiveMember(){if(!canEdit.value)return;if(personIdentity!==contextIdentity()){toast('账号或家族已切换，请重新选择成员。','ph-warning-circle');return};const m=store.members.find(m=>m.id===activeMember.value?.id);if(!m){toast('该成员已删除，请重新选择成员。','ph-warning-circle');return};openDialog('reminderDialog');reminderForm.memberId=m.id;reminderForm.title=m.name+(m.deceased&&m.deathDate?'忌日':'生日');reminderForm.type=m.deceased&&m.deathDate?'memorial':'birthday';reminderForm.date=m.deceased&&m.deathDate?m.deathDate:m.birthday||''}
  const personInfo=computed(()=>{
    const m=activeMember.value||{},birth=m.birthYear||Number((m.birthday||'').slice(0,4)),death=m.deathYear
    return {relation:`${m.relation||'家族成员'}${m.avatarName?' · '+m.avatarName:''}`,years:birth?`${birth}—${death||(m.deceased?'卒年待补':'今')}`:death?`生年待补—${death}`:'生卒资料尚待补充',lifespan:`${birth?`生于 ${birth} 年`:'生年待补充'} · ${death?`卒于 ${death} 年`:m.deceased?'卒年待补充':'健在'}`,birthday:m.birthday?`公历 ${m.birthday}${lunarInfo(m.birthday).full?' · 农历'+lunarInfo(m.birthday).full:''}${m.deathDate?' · 忌日 '+m.deathDate:''}`:`具体出生日期尚待补充${m.deathDate?' · 忌日 '+m.deathDate:''}`,bio:m.bio||'尚未记录生平事迹，可点击“编辑资料”补充其经历与贡献。'}
  })
  const relationMode=ref('name'),relationNameA=ref(''),relationNameB=ref(''),relationYearA=ref(''),relationYearB=ref(''),homeResult=ref(null),dialogResult=ref(null)
  function analyzeHome(){homeResult.value=relationMode.value==='name'?analyzeNames(store.members,relationNameA.value,relationNameB.value):inferRelationshipByYears(relationYearA.value,relationYearB.value)}
  function startSelection(){if(store.members.length<2)return;showPage('genealogy');setTreeView('tree');selecting.value=true;toast('请依次点击两位成员图标','ph-git-branch')}
  function chooseAgain(){closeDialog();startSelection()}
  const calendarYear=ref(today.value.getFullYear()),calendarMonth=ref(today.value.getMonth())
  const calendarLunarSummary=computed(()=>{const months=[];for(let d=1;d<=new Date(calendarYear.value,calendarMonth.value+1,0).getDate();d++){const key=lunarInfo(new Date(calendarYear.value,calendarMonth.value,d,12)).monthKey;if(!months.includes(key))months.push(key)}return '农历'+months.join(' / ')})
  const calendarCells=computed(()=>calendarDays(calendarYear.value,calendarMonth.value,store.reminders,dateString(today.value)))
  function changeMonth(n){const d=new Date(calendarYear.value,calendarMonth.value+n,1);calendarYear.value=d.getFullYear();calendarMonth.value=d.getMonth()}
  function openReminderDate(date){openDialog('reminderDialog');reminderForm.date=date}
  const timelineReminders=computed(()=>reminderViews(store.reminders.map(r=>({...r,member:store.members.find(m=>m.id===r.memberId)?.name||r.member||''})),today.value))
  const upcomingReminders=computed(()=>timelineReminders.value.filter(r=>r.days!==null&&r.days>=0))
  const homeReminders=computed(()=>upcomingReminders.value.slice(0,3))
  const nextFestival=computed(()=>upcomingReminders.value.find(r=>r.type==='festival'))
  function setReminderCalendar(type){if(type==='qingming'){reminderForm.type='festival';reminderForm.repeat='每年';reminderForm.date=qingmingDate(Number(reminderForm.date.slice(0,4))||today.value.getFullYear())}}
  function editReminder(r){if(!canEdit.value)return;formIdentity=contextIdentity();Object.assign(reminderForm,emptyReminder(),r,{memberId:r.memberId||'',advance:typeof r.advance==='number'?(r.advance?'提前'+r.advance+'天':'当天'):String(r.advance||'当天').replace(/\s/g,'')});dialog.value='reminderDialog'}
  async function submitReminder(){
    if(saveBusy.value)return
    saveBusy.value=true
    try{assertFormContext();assertEditable();if(!reminderForm.title.trim())throw Error('请填写提醒名称。');if(!parseDate(reminderForm.date))throw Error('请选择有效的日期。');if(reminderForm.memberId&&!store.members.some(m=>m.id===reminderForm.memberId))throw Error('关联成员已删除，请重新选择。');const {lunar_month,lunar_day,is_leap,member,...fields}=reminderForm;const raw={...fields,lunar:reminderLunar.value};const result=await saveReminder(raw);assertFormContext();writeStorage('family-last-reminder',raw);saveBusy.value=false;closeDialog();toast(`“${raw.title}”${savedMessage(result)}`,'ph-calendar-check')}catch(e){toast(e.message,'ph-warning-circle')}finally{saveBusy.value=false}
  }
  async function removeReminder(r){if(!canEdit.value||saveBusy.value||!await confirmAction('删除提醒',`确认删除“${r.title}”？`))return;saveBusy.value=true;try{const result=await deleteReminder(r.id);toast('提醒已删除，'+savedMessage(result),'ph-trash')}catch(e){toast(e.message,'ph-warning-circle')}finally{saveBusy.value=false}}
  const {loginForm,loginMethod,maskedLoginPhone,loginBusy,loginError,setLoginMode,sendLoginSms,smsCountdown,smsSending,submitLogin,resetLoginForm}=useLoginForm({
    dialog,initialError:store.error||'',notify:toast,
    async onLogin(account,remember,details){
      manualLogin=true
      try {
        await activateSession({...account,loggedAt:Date.now(),storage:remember?'local':'session'},remember)
        refreshNotifications().catch(()=>{})
        homeResult.value=null;search.value='';if(currentPage.value==='genealogy')setTreeView('tree')
        guidedSession=store.session?.accessToken||''
        const nextDialog=await familyGuides.beginLoginGuide(details)
        return {dialog:nextDialog}
      } finally { manualLogin=false }
    }
  })
  watch(()=>[store.sessionRestoring,store.session],([restoring,session])=>{
    if(restoring||loginBusy.value)return
    if(session){if(dialog.value==='loginDialog')dialog.value=''}
    else{loginError.value=store.error||'';dialog.value='loginDialog'}
  },{immediate:true})
  watch(()=>[store.sessionRestoring,store.sessionValidated,store.session?.accessToken],async([restoring,validated,token])=>{
    if(restoring||!validated||!token||manualLogin||token===guidedSession)return
    guidedSession=token
    const nextDialog=await familyGuides.beginLoginGuide({restored:true})
    if(nextDialog&&!dialog.value)dialog.value=nextDialog
  },{immediate:true})
  watch(()=>store.session?.accessToken,()=>{guidedSession='';familyGuides.clearFamilyGuide()},{flush:'sync'})
  function enterGuestMode(){if(loginBusy.value||smsSending.value)return;resetLoginForm();enterGuest();clearSelection();dialog.value='';toast('已进入访客模式，仅可浏览家谱内容','ph-eye')}
  async function loginAction(){
    if(loginBusy.value||saveBusy.value||avatarBusy.value||familySharing.value?.busy||familyGuides.familyGuideBusy.value)return
    loginBusy.value=true
    let message=''
    try{
      if(store.session){try{const result=await logout();message=store.error||(result?.serverRevoked===false?'已退出本机，服务器会话撤销失败，请稍后检查登录设备。':'已退出登录，家谱缓存仍保留')}catch(e){message=e.message}}
      clearSelection();resetLoginForm();loginError.value='';dialog.value='loginDialog'
      if(message)toast(message,'ph-sign-out')
    }finally{loginBusy.value=false}
  }
  const profileForm=reactive({name:'',avatar:''}),avatarUrls=reactive({})
  let avatarGeneration=0
  watch(()=>[store.session?.accountId,store.profile.avatar,profileForm.avatar],async values=>{const generation=++avatarGeneration;for(const avatar of values.slice(1).filter(Boolean)){try{const url=await resolveAvatar(avatar);if(generation===avatarGeneration)avatarUrls[avatar]=url}catch{if(generation===avatarGeneration)avatarUrls[avatar]=''}}},{immediate:true})
  const accountAvatarText=name=>String(name||'我的家谱').replace(/氏家族$|家族$/u,'').trim().slice(0,1)||'谱'
  const avatarStyle=avatar=>({backgroundImage:avatarUrls[avatar]?`url("${avatarUrls[avatar]}")`:avatar&&/^(data:image|\/static\/)/.test(avatar)?`url("${avatar}")`:''})
  function editProfile(){if(!canEdit.value)return;formIdentity=contextIdentity();Object.assign(profileForm,store.profile);dialog.value='profileDialog'}
  async function applyAvatar(file,path){
    if(avatarBusy.value)return
    avatarBusy.value=true
    try{
      assertFormContext();if(dialog.value!=='profileDialog')throw Error('头像编辑表单已关闭，请重新选择图片。')
      if(file.size>2*1024*1024)throw Error('头像图片不能超过 2MB')
      if(file.name&&!/\.(jpe?g|png|webp)$/i.test(file.name))throw Error('请选择 JPG、PNG 或 WEBP 图片')
      const avatar=await persistAvatar(path);assertFormContext();profileForm.avatar=avatar
    }catch(e){toast(e.message,'ph-warning-circle')}finally{avatarBusy.value=false}
  }
  // #ifdef H5
  let avatarInput=null
  function removeAvatarInput(){avatarInput?.remove();avatarInput=null}
  onUnmounted(removeAvatarInput)
  // #endif
  function chooseAvatar(){if(avatarBusy.value||saveBusy.value)return;
    // #ifdef H5
    // 在原生按钮的点击事件中同步打开选择器，避开 uni 的弹窗交互状态判断。
    removeAvatarInput()
    const input=document.createElement('input')
    input.type='file';input.accept='image/jpeg,image/png,image/webp';input.hidden=true
    avatarInput=input
    input.addEventListener('cancel',removeAvatarInput,{once:true})
    input.addEventListener('change',()=>{
      const file=input.files?.[0]
      removeAvatarInput()
      if(file)applyAvatar(file,file)
    },{once:true})
    document.body.appendChild(input)
    input.click()
    return
    // #endif
    // #ifndef H5
    uni.chooseImage({count:1,sizeType:['original'],success:result=>{
      const file=result.tempFiles[0]
      if(file)applyAvatar(file,result.tempFilePaths[0])
    },fail:error=>{if(!/cancel/i.test(error.errMsg||''))toast('头像选择失败，请重试。','ph-warning-circle')}})
    // #endif
  }
  async function submitProfile(){if(saveBusy.value||avatarBusy.value)return;saveBusy.value=true;try{assertFormContext();assertEditable();if(!profileForm.name.trim())throw Error('名称不能为空');const result=await saveProfile(profileForm);assertFormContext();saveBusy.value=false;closeDialog();toast('头像与名称'+savedMessage(result))}catch(e){toast(e.message,'ph-warning-circle')}finally{saveBusy.value=false}}
  async function clearDemo(){if(!canEdit.value||saveBusy.value||!await confirmAction('清空当前家谱','将删除当前家族的成员、关系、纪念日和家族资料，确认继续？'))return;saveBusy.value=true;try{const result=await clearCurrentData();toast('当前家谱已清空，'+savedMessage(result),'ph-trash')}catch(e){toast(e.message,'ph-warning-circle')}finally{saveBusy.value=false}}
  async function exportPendingChanges(){try{const data=await exportFamilyData();const result=await downloadJson(data);toast(result?.path?'本机修改已导出':'本机修改备份已生成','ph-download-simple')}catch(e){toast(e.message,'ph-warning-circle')}}
  async function discardPending(){if(!await confirmAction('放弃本机待同步修改','将恢复到云端最后版本，本机未同步修改会被移除。确认继续？'))return;discardPendingChanges();toast('已放弃本机待同步修改','ph-check-circle')}
  return {legalDocument,openLegal,closeLegal,...familyGuides,familySharing,formRelations,personRelations,viewRelatedPerson,store,accountTools,canEdit,saveBusy,avatarBusy,theme,setTheme,elderMode,setElderMode,toolsTab,openTools,unreadNotifications,syncLabel,conflictDetails,syncNow,resolveConflict,relationOptions,relatedMemberOptions,setReminderCalendar,editReminder,removeActiveMember,currentPage,pageTitles,todayLabel,generationCount,showPage,scrollMain,openDialog,closeDialog,avatarStyle,accountAvatarText,loginAction,enterGuestMode,editProfile,toast,clearDemo,exportPendingChanges,discardPending,treeView,search,filteredMembers,selectedNames,selectedMemberNames,selectedLabels,selecting,selectionNote,setTreeView,resetTree,startSelection,chooseAgain,pickPerson,demoMembers,userTree,demoTree,relationMode,relationNameA,relationNameB,relationYearA,relationYearB,memberNames,relationMemberOptions,homeResult,analyzeHome,calendarYear,calendarMonth,calendarLunarSummary,calendarCells,changeMonth,openReminderDate,upcomingReminders,homeReminders,nextFestival,timelineReminders,removeReminder,dialog,memberForm,editingId,memberLunar,submitMember,reminderForm,reminderLunar,reminderMemberOptions,loginForm,loginMethod,maskedLoginPhone,loginBusy,loginError,setLoginMode,sendLoginSms,smsCountdown,smsSending,submitLogin,profileForm,chooseAvatar,submitProfile,activeMember,personInfo,editActiveMember,remindActiveMember,dialogResult,toastState}
}
