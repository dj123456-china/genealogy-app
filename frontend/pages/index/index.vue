<template>
<view :class="['parity-root', 'supports-flex-gap', { 'theme-dark': theme === 'dark', 'elder-mode': elderMode }]">
<NativeText @click="scrollMain()" class="skip-link el-a">跳到主要内容</NativeText>
<view :class="{ 'auth-locked': !store.session }" class="app-shell el-div">
<view aria-label="主导航" class="sidebar el-aside">
<NativeButton @click="showPage('home')" aria-label="返回首页" class="brand el-button" data-page-link="home">
<NativeText aria-hidden="true" class="brand-mark el-span">谱</NativeText>
<NativeText class="el-span"><NativeText class="el-strong">家谱制作器</NativeText><NativeText class="el-small">宗谱档案管理</NativeText></NativeText>
</NativeButton>
<view class="side-nav el-nav">
<NativeButton :class="{ active: currentPage === 'home' }" @click="showPage('home')" class="nav-item el-button" data-page-link="home">
<NativeText aria-hidden="true" class="ph ph-house-line el-i"></NativeText><NativeText class="el-span">首页</NativeText>
</NativeButton>
<NativeButton :class="{ active: currentPage === 'genealogy' }" @click="showPage('genealogy')" class="nav-item el-button" data-page-link="genealogy">
<NativeText aria-hidden="true" class="ph ph-tree-structure el-i"></NativeText><NativeText class="el-span">家族谱</NativeText>
</NativeButton>
<NativeButton :class="{ active: currentPage === 'reminders' }" @click="showPage('reminders')" class="nav-item el-button" data-page-link="reminders">
<NativeText aria-hidden="true" class="ph ph-calendar-dots el-i"></NativeText><NativeText class="el-span">纪念日</NativeText>
</NativeButton>
<NativeButton :class="{ active: currentPage === 'account' }" @click="showPage('account')" class="nav-item el-button" data-page-link="account">
<NativeText aria-hidden="true" class="ph ph-user-circle el-i"></NativeText><NativeText class="el-span">我的</NativeText>
</NativeButton>
</view>
<NativeButton @click="showPage('account')" class="profile-chip el-button" data-page-link="account">
<NativeText :class="{ 'has-image': !!store.profile.avatar }" :style="avatarStyle(store.profile.avatar)" aria-label="家族头像" class="avatar avatar-text account-avatar el-span">{{ store.profile.avatar ? '' : accountAvatarText(store.profile.name) }}</NativeText>
<NativeText class="el-span"><NativeText class="el-strong">{{ store.profile.name }}</NativeText><NativeText class="el-small" id="accountLoginStatus">{{ store.guest ? '访客浏览' : store.session ? '已登录 · ' + store.session.username : '未登录' }}</NativeText></NativeText>
<NativeText aria-hidden="true" class="ph ph-caret-right el-i"></NativeText>
</NativeButton>
</view>
<view class="mobile-header el-header">
<NativeButton @click="showPage('home')" class="brand compact el-button" data-page-link="home">
<NativeText aria-hidden="true" class="brand-mark el-span">谱</NativeText><NativeText class="el-strong">家谱制作器</NativeText>
</NativeButton>
<NativeButton :aria-label="store.guest ? '退出访客并登录' : store.session ? '退出登录' : '登录'" :class="{}" @click="loginAction()" class="icon-btn mobile-login-button el-button" id="mobileLoginButton"><NativeText :class="store.session && !store.guest ? 'ph-sign-out' : 'ph-sign-in'" class="ph el-i"></NativeText></NativeButton>
</view>
<view class="main-content el-main" id="mainContent" tabindex="-1">
<view class="topbar el-header">
<view class="el-div">
<view class="date-line el-p" id="todayLine">{{ todayLabel }}</view>
<view class="el-h1" id="pageTitle">{{ pageTitles[currentPage] }}</view>
</view>
<view class="topbar-actions el-div">
<NativeButton @click="openTools('notifications')" aria-label="查看通知" class="icon-btn notification-btn el-button" data-page-link="reminders">
<NativeText class="ph ph-bell el-i"></NativeText><NativeText v-if="unreadNotifications" :aria-label="unreadNotifications + ' 条未读通知'" class="notify-dot el-span"></NativeText>
</NativeButton>
<NativeButton :aria-label="store.guest ? '退出访客并登录' : store.session ? '退出登录' : '登录'" :class="{ 'btn-primary': !store.session || store.guest, 'btn-secondary': !!store.session && !store.guest }" @click="loginAction()" class="btn global-login-button el-button" id="globalLoginButton"><NativeText :class="store.session && !store.guest ? 'ph-sign-out' : 'ph-sign-in'" class="ph el-i"></NativeText><NativeText class="el-span">{{ store.guest ? '登录' : store.session ? '退出' : '登录' }}</NativeText></NativeButton>
<NativeButton :disabled="!canEdit" @click="openDialog('memberDialogForm')" class="btn btn-primary el-button" data-open-dialog="memberDialogForm">
<NativeText aria-hidden="true" class="ph ph-user-plus el-i"></NativeText>录入家人
            </NativeButton>
</view>
</view>
<view v-if="store.session && !store.guest" class="sync-banner" :class="{'is-error':store.error || store.syncStatus === 'conflict'}" role="status">
<view class="sync-description"><NativeText>{{ syncLabel }}{{ store.role === 'VIEWER' ? ' · 当前家族只读' : '' }}</NativeText><view v-if="store.error" class="form-hint">{{ store.error }}</view></view>
<NativeButton v-if="store.syncStatus !== 'loading' && store.syncStatus !== 'saving' && store.syncStatus !== 'conflict'" @click="syncNow()" class="btn btn-secondary">立即同步</NativeButton>
<template v-if="store.permissionLost && store.syncStatus === 'error'"><NativeButton @click="exportPendingChanges()" class="btn btn-secondary">导出本机修改</NativeButton><NativeButton @click="discardPending()" class="btn btn-secondary">放弃本机修改</NativeButton></template>
<template v-if="store.syncStatus === 'conflict'"><NativeButton :disabled="!canEdit" @click="resolveConflict('local')" class="btn btn-secondary">保留本机冲突资料</NativeButton><NativeButton @click="resolveConflict('remote')" class="btn btn-secondary">采用云端冲突资料</NativeButton><view class="sync-conflict-details">{{ conflictDetails || '双方修改发生冲突。选择处理方式后继续同步；当前资料已在本机保留。' }}</view></template>
</view>
<view :class="{ active: currentPage === 'home' }" aria-labelledby="homeHeading" class="page el-section" data-page="home">
<view class="hero-panel el-article">
<NativeImage alt="页面视觉示意图，非真实家族照片" class="el-img" mode="aspectFill" src="/static/assets/family-cover.jpg"/>
<view class="hero-scrim el-div"></view>
<view class="hero-copy el-div">
<NativeText class="eyebrow el-span">{{ store.profile.name }} · 数字典藏</NativeText>
<view class="el-h2" id="homeHeading">修谱存史<NativeText class="el-br">{{ '\n' }}</NativeText>敬宗睦族</view>
<view class="el-p">谨录世系、生平与纪念日，保存完整可靠的家族档案。</view>
<view class="hero-actions el-div">
<NativeButton @click="showPage('genealogy')" class="btn btn-paper el-button" data-page-link="genealogy">查看家族谱</NativeButton>
<NativeButton :disabled="!canEdit" @click="openDialog('memberDialogForm')" class="btn btn-ghost-light el-button" data-open-dialog="memberDialogForm">添加成员</NativeButton>
</view>
</view>
<view aria-hidden="true" class="hero-seal el-div"><NativeText class="el-span">{{ accountAvatarText(store.profile.name) }}氏</NativeText><NativeText class="el-small">家谱</NativeText></view>
</view>
<view aria-label="家谱概览" class="stats-strip el-div">
<view class="el-div"><NativeText class="stat-icon el-span"><NativeText class="ph ph-users-three el-i"></NativeText></NativeText><view class="el-p"><NativeText class="el-strong" id="memberCount">{{ store.members.length }}</NativeText><NativeText class="el-small">已录入成员</NativeText></view></view>
<view class="el-div"><NativeText class="stat-icon el-span"><NativeText class="ph ph-git-branch el-i"></NativeText></NativeText><view class="el-p"><NativeText class="el-strong" id="generationCount">{{ generationCount }}</NativeText><NativeText class="el-small">已整理世代</NativeText></view></view>
</view>
<view class="home-grid el-div">
<view class="content-block reminder-block el-section">
<view class="section-heading el-div">
<view class="el-div"><view class="el-h3">近期重要日子</view><view class="el-p">生日、忌日和传统祭日集中提醒</view></view>
<NativeButton @click="showPage('reminders')" class="text-btn el-button" data-page-link="reminders">查看全部 <NativeText class="ph ph-arrow-right el-i"></NativeText></NativeButton>
</view>
<view class="event-list el-div" id="homeEventList">
<view v-if="!homeReminders.length" class="reminder-empty el-div"><view class="el-h3">暂无近期提醒</view><view class="el-p">添加生日、忌日或祭日提醒后，将在这里显示。</view><NativeButton :disabled="!canEdit" @click="openDialog('reminderDialog')" class="btn btn-secondary el-button">添加提醒</NativeButton></view>
<NativeButton v-for="reminder in homeReminders" :key="reminder.id" @click="showPage('reminders')" class="event-row el-button">
<NativeText class="el-time"><NativeText class="el-strong">{{ reminder.occurrence.slice(8) }}</NativeText><NativeText class="el-small">{{ Number(reminder.occurrence.slice(5,7)) }}月</NativeText></NativeText>
<NativeText :class="reminder.type" class="event-type el-span"><NativeText :class="reminder.type === 'birthday' ? 'ph-cake' : reminder.type === 'memorial' ? 'ph-flower-lotus' : 'ph-leaf'" class="ph el-i"></NativeText></NativeText>
<NativeText class="event-copy el-span"><NativeText class="el-strong">{{ reminder.title }}</NativeText><NativeText class="el-small">{{ reminder.description }}</NativeText></NativeText><NativeText class="countdown el-span">{{ reminder.countdown }}</NativeText>
</NativeButton>
</view>
</view>
<view class="content-block festival-card el-aside">
<view class="festival-top el-div"><NativeText class="el-span">祭日安排</NativeText><NativeText class="ph ph-bell-ringing el-i"></NativeText></view>
<view v-if="nextFestival" class="el-div"><view class="el-h3">{{ nextFestival.title }}</view><view class="el-p">{{ nextFestival.displayDate }} · {{ nextFestival.countdown }}</view><view class="el-p">{{ nextFestival.description }}</view></view>
<view v-else class="reminder-empty el-div"><view class="el-h3">暂无祭日安排</view><view class="el-p">尚未添加祭日提醒。</view></view>
<NativeButton v-if="nextFestival" @click="showPage('reminders')" class="btn btn-primary full el-button">查看祭日安排</NativeButton>
<NativeButton v-else :disabled="!canEdit" @click="openDialog('reminderDialog'); reminderForm.type = 'festival'" class="btn btn-primary full el-button">添加祭日提醒</NativeButton>
</view>
</view>
<view aria-labelledby="relationAnalysisHeading" class="content-block relation-analysis-entry el-section" id="relationAnalysis">
<view class="section-heading relation-entry-heading el-div">
<view class="el-div"><NativeText class="eyebrow dark el-span">关系核验</NativeText><view class="el-h3" id="relationAnalysisHeading">成员关系分析</view><view class="el-p">可按已录入的成员姓名核验关系，或仅按出生年份进行推测。</view></view>
<NativeText aria-hidden="true" class="relation-entry-icon el-span"><NativeText class="ph ph-git-branch el-i"></NativeText></NativeText>
</view>
<view aria-label="关系分析方式" class="relation-mode-tabs el-div" role="tablist">
<NativeButton :aria-selected="relationMode === 'name'" :class="{ active: relationMode === 'name' }" @click="relationMode = 'name'" aria-selected="true" class="el-button" data-relation-mode="name" role="tab">按成员姓名</NativeButton>
<NativeButton :aria-selected="relationMode === 'year'" :class="{ active: relationMode === 'year' }" @click="relationMode = 'year'" aria-selected="false" class="el-button" data-relation-mode="year" role="tab">按出生年份</NativeButton>
</view>
<NativeForm class="relation-query-form el-form" id="relationNameForm" v-show="relationMode === 'name'">
<view class="el-label"><NativeText class="el-span">第一人</NativeText><NativeField :options="relationMemberOptions" kind="select" @confirm="analyzeHome()" class="el-select" id="relationNameA" name="personA" required="" v-model="relationNameA"/></view>
<NativeText aria-hidden="true" class="relation-link el-span"><NativeText class="ph ph-arrows-left-right el-i"></NativeText></NativeText>
<view class="el-label"><NativeText class="el-span">第二人</NativeText><NativeField :options="relationMemberOptions" kind="select" @confirm="analyzeHome()" class="el-select" id="relationNameB" name="personB" required="" v-model="relationNameB"/></view>
<NativeButton @click="analyzeHome()" class="btn btn-primary el-button"><NativeText class="ph ph-git-branch el-i"></NativeText>分析关系</NativeButton>
</NativeForm>
<NativeForm class="relation-query-form el-form" id="relationYearForm" v-show="relationMode === 'year'">
<view class="el-label"><NativeText class="el-span">第一人出生年份</NativeText><NativeField @confirm="analyzeHome()" class="el-input" id="relationYearA" inputmode="numeric" max="2099" min="1000" name="yearA" placeholder="例如：1965" required="" type="number" v-model="relationYearA"/></view>
<NativeText aria-hidden="true" class="relation-link el-span"><NativeText class="ph ph-arrows-left-right el-i"></NativeText></NativeText>
<view class="el-label"><NativeText class="el-span">第二人出生年份</NativeText><NativeField @confirm="analyzeHome()" class="el-input" id="relationYearB" inputmode="numeric" max="2099" min="1000" name="yearB" placeholder="例如：1992" required="" type="number" v-model="relationYearB"/></view>
<NativeButton @click="analyzeHome()" class="btn btn-secondary el-button"><NativeText class="ph ph-sparkle el-i"></NativeText>推测关系</NativeButton>
</NativeForm>
<NativeField :names="memberNames" class="el-datalist" id="familyMemberNames" kind="datalist"></NativeField>
<NativeText class="relation-field-hint el-small">关系查询按具体成员档案核验，同名成员请按亲属称谓和世代选择；出生年份结果仅作年龄差推测。</NativeText>
<RelationResult :result="homeResult" id="relationHomeResult"></RelationResult>
</view>
</view>
<view :class="{ active: currentPage === 'genealogy' }" aria-labelledby="genealogyHeading" class="page el-section" data-page="genealogy">
<view class="page-intro el-div">
<view class="el-div"><NativeText class="eyebrow dark el-span">家族脉络</NativeText><view class="el-h2" id="genealogyHeading">{{ store.profile.name }} · 族谱</view><view class="el-p">这里只显示你录入的家人，示范族谱可随时单独查看。</view></view>
<view class="intro-actions el-div">
<NativeButton :disabled="treeView !== 'tree' || store.members.length < 2" @click="startSelection()" class="btn btn-secondary el-button" id="relationSelectButton"><NativeText class="ph ph-cursor-click el-i"></NativeText>选择两人</NativeButton>
<NativeButton :disabled="!canEdit" @click="openDialog('memberDialogForm')" class="btn btn-primary el-button" data-open-dialog="memberDialogForm"><NativeText class="ph ph-plus el-i"></NativeText>添加成员</NativeButton>
</view>
</view>
<view class="tree-toolbar el-div">
<view class="search-box el-div"><NativeText class="ph ph-magnifying-glass el-i"></NativeText><view class="sr-only el-label" for="memberSearch">搜索成员</view><NativeField class="el-input" id="memberSearch" placeholder="搜索姓名或关系" type="search" v-model="search"/></view>
<view aria-label="族谱视图" class="segmented el-div"><NativeButton :aria-pressed="treeView === 'tree'" :class="{ active: treeView === 'tree' }" @click="setTreeView('tree')" aria-pressed="true" class="el-button" data-tree-view="tree">家族树</NativeButton><NativeButton :aria-pressed="treeView === 'directory'" :class="{ active: treeView === 'directory' }" @click="setTreeView('directory')" aria-pressed="false" class="el-button" data-tree-view="directory">成员名录</NativeButton><NativeButton :aria-pressed="treeView === 'demo'" :class="{ active: treeView === 'demo' }" @click="setTreeView('demo')" aria-pressed="false" class="el-button" data-tree-view="demo">示范</NativeButton></view>
<NativeButton :disabled="treeView === 'directory'" @click="resetTree()" aria-label="居中族谱" class="icon-btn el-button" id="resetTree"><NativeText class="ph ph-crosshair el-i"></NativeText></NativeButton>
</view>
<view :class="{ 'is-active': selecting }" class="tree-selection-note el-p" id="treeSelectionNote"><NativeText class="ph ph-git-branch el-i"></NativeText><NativeText class="el-span">{{ selectionNote }}</NativeText></view>
<view class="tree-demo-notice el-div" id="treeDemoNotice" v-show="treeView === 'demo'">
<NativeText aria-hidden="true" class="tree-demo-mark el-span">例</NativeText>
<view class="el-div"><NativeText class="el-strong">示范族谱</NativeText><view class="el-p">下面内容只用于展示排版和关系线，不会写入你的家谱。</view></view>
<NativeButton :disabled="!canEdit" @click="setTreeView('tree'); openDialog('memberDialogForm')" class="btn btn-secondary btn-small el-button" id="startOwnTree"><NativeText class="ph ph-pencil-simple el-i"></NativeText>开始录入我的家谱</NativeButton>
</view>
<FamilyTree :editable="canEdit" :members="store.members" :search="search" :selected="selectedNames" @add="openDialog('memberDialogForm')" @person="pickPerson" ref="userTree" v-show="treeView === 'tree'"></FamilyTree>
<view aria-label="成员名录" class="member-directory el-section" id="memberDirectory" v-show="treeView === 'directory'"><view class="member-directory-empty el-div" v-if="!store.members.length"><NativeText class="ph ph-users-three el-i"></NativeText><NativeText class="el-strong">成员名录还是空的</NativeText><NativeText class="el-span">先录入第一位家人，示范成员不会出现在这里。</NativeText></view><NativeButton :data-person="member.name" :key="member.id" @click="pickPerson(member)" class="directory-row el-button" v-for="member in filteredMembers"><NativeText class="avatar avatar-text el-span">{{ member.avatarLabel || member.name.slice(-1) }}</NativeText><NativeText class="el-span"><NativeText class="el-strong">{{ member.name }}</NativeText><NativeText class="el-small">{{ member.avatarName || member.relation }}</NativeText></NativeText><NativeText class="ph ph-arrow-right el-i"></NativeText></NativeButton></view>
<FamilyTree :members="demoMembers" :search="search" demo="" ref="demoTree" v-show="treeView === 'demo'"></FamilyTree>
</view>
<view :class="{ active: currentPage === 'reminders' }" aria-labelledby="reminderHeading" class="page el-section" data-page="reminders">
<view class="page-intro el-div">
<view class="el-div"><NativeText class="eyebrow dark el-span">家族日历</NativeText><view class="el-h2" id="reminderHeading">重要日子，集中记录</view><view class="el-p">支持按公历、农历或清明节气重复，记录生日、忌日和传统祭日。</view></view>
<NativeButton :disabled="!canEdit" @click="openDialog('reminderDialog')" class="btn btn-primary el-button" data-open-dialog="reminderDialog"><NativeText class="ph ph-calendar-plus el-i"></NativeText>新建提醒</NativeButton>
</view>
<view class="calendar-layout el-div">
<view class="calendar-card el-section">
<view class="calendar-header el-div"><NativeButton @click="changeMonth(-1)" aria-label="上个月" class="icon-btn el-button" id="prevMonth"><NativeText class="ph ph-caret-left el-i"></NativeText></NativeButton><view class="calendar-header-title el-div"><NativeText class="el-strong" id="calendarMonth">{{ calendarYear + ' 年 ' + (calendarMonth + 1) + ' 月' }}</NativeText><NativeText class="el-small" id="calendarLunarMonth">{{ calendarLunarSummary }}</NativeText></view><NativeButton @click="changeMonth(1)" aria-label="下个月" class="icon-btn el-button" id="nextMonth"><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton></view>
<view class="week-row el-div"><NativeText class="el-span">一</NativeText><NativeText class="el-span">二</NativeText><NativeText class="el-span">三</NativeText><NativeText class="el-span">四</NativeText><NativeText class="el-span">五</NativeText><NativeText class="el-span">六</NativeText><NativeText class="el-span">日</NativeText></view>
<view class="date-grid el-div" id="dateGrid"><NativeButton :aria-label="cell.label" :class="{ 'muted-date': cell.muted, today: cell.today }" :key="cell.date" :title="cell.label" @click="openReminderDate(cell.date)" class="date-cell el-button" v-for="cell in calendarCells"><NativeText class="el-span">{{ cell.day }}</NativeText><NativeText class="lunar el-span">{{ cell.lunar }}</NativeText><NativeText class="date-mark el-span" v-if="cell.type"><NativeText :class="cell.type" class="el-i"></NativeText></NativeText></NativeButton></view>
<view class="calendar-legend el-div"><NativeText class="el-span"><NativeText class="legend-mark birthday el-i"></NativeText>生日</NativeText><NativeText class="el-span"><NativeText class="legend-mark memorial el-i"></NativeText>忌日</NativeText><NativeText class="el-span"><NativeText class="legend-mark festival el-i"></NativeText>传统祭日</NativeText></view>
</view>
<view class="upcoming-panel el-section">
<view class="section-heading el-div"><view class="el-div"><view class="el-h3">接下来的提醒</view><view class="el-p">提醒同步到当前家族，可编辑、删除和接收站内通知</view></view></view>
<view class="timeline el-div" id="reminderTimeline"><view v-if="!timelineReminders.length" class="reminder-empty el-div"><view class="el-h3">暂无纪念日提醒</view><view class="el-p">点击“新建提醒”添加自己的重要日子。</view></view><view :data-reminder-id="reminder.id" :key="reminder.id" class="el-article" v-for="reminder in timelineReminders"><NativeText :class="reminder.type" class="timeline-dot el-span"></NativeText><NativeText class="el-time">{{ reminder.displayDate }}<NativeText class="el-small">{{ reminder.countdown }}</NativeText></NativeText><view class="el-div"><NativeText class="el-strong">{{ reminder.title }}</NativeText><view class="el-p">{{ reminder.description }}</view><NativeText class="tag el-span">{{ reminder.tag }}</NativeText></view><view class="reminder-actions"><NativeButton :disabled="!canEdit || saveBusy" @click="editReminder(reminder)" aria-label="编辑提醒" class="icon-btn el-button"><NativeText class="ph ph-pencil-simple el-i"></NativeText></NativeButton><NativeButton :disabled="!canEdit || saveBusy" @click="removeReminder(reminder)" aria-label="删除提醒" class="icon-btn el-button"><NativeText class="ph ph-trash el-i"></NativeText></NativeButton></view></view></view>
</view>
</view>
</view>
<view :class="{ active: currentPage === 'account' }" aria-labelledby="accountHeading" class="page el-section" data-page="account">
<view class="account-hero el-div">
<NativeText :class="{ 'has-image': !!store.profile.avatar }" :style="avatarStyle(store.profile.avatar)" aria-label="家族头像" class="avatar avatar-text large account-avatar el-span">{{ store.profile.avatar ? '' : accountAvatarText(store.profile.name) }}</NativeText><view class="el-div"><view class="el-h2" id="accountHeading">{{ store.profile.name }}</view><view class="el-p" id="accountSessionText">{{ store.guest ? '访客浏览' : store.session ? '已登录 · ' + store.session.username + '（' + syncLabel + '）' : '本机资料 · 当前未登录' }}</view></view><view class="account-hero-actions el-div"><NativeButton :aria-label="store.guest ? '退出访客并登录' : store.session ? '退出登录' : '登录'" :class="{ 'btn-primary': !store.session || store.guest, 'btn-secondary': !!store.session && !store.guest }" @click="loginAction()" class="btn el-button" id="accountLoginButton"><NativeText :class="store.session && !store.guest ? 'ph-sign-out' : 'ph-sign-in'" class="ph el-i"></NativeText><NativeText class="el-span">{{ store.guest ? '登录' : store.session ? '退出' : '登录' }}</NativeText></NativeButton><NativeButton :disabled="!canEdit" @click="editProfile()" class="btn btn-secondary el-button" id="editProfile"><NativeText class="ph ph-pencil-simple el-i"></NativeText>自定义头像与名称</NativeButton></view>
</view>
<FamilySharing ref="familySharing" :active="currentPage === 'account'" @toast="toast" />
<view class="account-grid el-div">
<view v-if="store.guest" class="membership-card el-section"><NativeText class="plan-icon el-span"><NativeText class="ph ph-eye el-i"></NativeText></NativeText><view class="el-div"><NativeText class="eyebrow el-span">访客模式</NativeText><view class="el-h3">只读浏览</view><view class="el-p">无需登录即可浏览示范家谱、成员关系和纪念日。访客不能编辑或保存资料。</view></view></view>
<view v-else class="membership-card el-section"><NativeText class="plan-icon el-span"><NativeText class="ph ph-book-open-text el-i"></NativeText></NativeText><view class="el-div"><NativeText class="eyebrow el-span">云端资料</NativeText><view class="el-h3">家谱档案</view><view class="el-p">API 同步会把当前家谱保存到你的账号云端，换设备登录后可继续使用；网络不可用时先保留在本机，联网后再同步。</view></view></view>
<view class="settings-card el-section">
<view class="el-h3">{{ store.guest ? '访客帮助' : '账户与隐私' }}</view>
<view class="theme-setting"><view><NativeText class="el-strong">显示模式</NativeText><view class="form-hint">切换日间或夜间界面配色。</view></view><view class="theme-switch" role="group" aria-label="显示模式"><NativeButton class="btn btn-small" :class="{ 'btn-primary': theme === 'light', 'btn-secondary': theme !== 'light' }" @click="setTheme('light')"><NativeText class="ph ph-sun el-i"></NativeText>日间</NativeButton><NativeButton class="btn btn-small" :class="{ 'btn-primary': theme === 'dark', 'btn-secondary': theme !== 'dark' }" @click="setTheme('dark')"><NativeText class="ph ph-moon el-i"></NativeText>夜间</NativeButton></view></view>
<view class="accessibility-setting"><view><NativeText class="el-strong">助老模式</NativeText><view class="form-hint">放大文字、按钮和点击区域，适合视力不佳或触控不便时使用。</view></view><NativeButton class="elder-toggle" :class="{ active: elderMode }" role="switch" :aria-checked="elderMode" @click="setElderMode(!elderMode)"><NativeText class="elder-toggle-track"><NativeText class="elder-toggle-thumb"></NativeText></NativeText><NativeText class="elder-toggle-label">{{ elderMode ? '已开启' : '未开启' }}</NativeText></NativeButton></view>
<template v-if="store.guest">
<NativeButton @click="openTools('privacy')" class="el-button" id="guestGuideSetting"><NativeText class="el-span"><NativeText class="ph ph-book-open-text el-i"></NativeText><NativeText class="el-strong">查看使用说明与功能</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
</template>
<template v-else>
<NativeButton @click="openTools('privacy')" class="el-button" id="privacySetting"><NativeText class="el-span"><NativeText class="ph ph-shield-check el-i"></NativeText><NativeText class="el-strong">隐私与授权</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton @click="openTools('phone')" class="el-button"><NativeText class="el-span"><NativeText class="ph ph-device-mobile el-i"></NativeText><NativeText class="el-strong">手机号与登录设备</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton @click="openFamilyGuides()" class="el-button" id="allFamilyGuides"><NativeText class="el-span"><NativeText class="ph ph-book-open-text el-i"></NativeText><NativeText class="el-strong">我的所有导览</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton @click="openTools('backup')" class="el-button"><NativeText class="el-span"><NativeText class="ph ph-download-simple el-i"></NativeText><NativeText class="el-strong">导入导出与操作日志</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton @click="openTools('delete')" class="el-button"><NativeText class="el-span"><NativeText class="ph ph-user-minus el-i"></NativeText><NativeText class="el-strong">注销账号</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton @click="loginAction()" class="el-button" id="logoutButton" v-if="store.session"><NativeText class="el-span"><NativeText class="ph ph-sign-out el-i"></NativeText><NativeText class="el-strong">退出登录</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton :disabled="!canEdit || saveBusy" @click="clearDemo()" class="el-button" id="clearDemo"><NativeText class="el-span"><NativeText class="ph ph-trash el-i"></NativeText><NativeText class="el-strong">清空当前家谱</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
</template>
<NativeButton @click="openLegal('disclaimer')" class="el-button" id="disclaimerSetting"><NativeText class="el-span"><NativeText class="ph ph-info el-i"></NativeText><NativeText class="el-strong">免责声明</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
<NativeButton @click="openLegal('rules')" class="el-button" id="rulesSetting"><NativeText class="el-span"><NativeText class="ph ph-book-open-text el-i"></NativeText><NativeText class="el-strong">使用规范</NativeText></NativeText><NativeText class="ph ph-caret-right el-i"></NativeText></NativeButton>
</view>
</view>
</view>
</view>
<view aria-label="移动端主导航" class="bottom-nav el-nav">
<NativeButton :class="{ active: currentPage === 'home' }" @click="showPage('home')" class="el-button" data-page-link="home"><NativeText class="ph ph-house-line el-i"></NativeText><NativeText class="el-span">首页</NativeText></NativeButton>
<NativeButton :class="{ active: currentPage === 'genealogy' }" @click="showPage('genealogy')" class="el-button" data-page-link="genealogy"><NativeText class="ph ph-tree-structure el-i"></NativeText><NativeText class="el-span">家族谱</NativeText></NativeButton>
<NativeButton :class="{ active: currentPage === 'reminders' }" @click="showPage('reminders')" class="el-button" data-page-link="reminders"><NativeText class="ph ph-calendar-dots el-i"></NativeText><NativeText class="el-span">纪念日</NativeText></NativeButton>
<NativeButton :class="{ active: currentPage === 'account' }" @click="showPage('account')" class="el-button" data-page-link="account"><NativeText class="ph ph-user-circle el-i"></NativeText><NativeText class="el-span">我的</NativeText></NativeButton>
</view>
</view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'memberDialogForm'"><view @click.stop aria-modal="true" class="app-dialog el-dialog" id="memberDialogForm" role="dialog" v-if="dialog === 'memberDialogForm'">
<NativeForm class="el-form" id="memberForm">
<view class="dialog-header el-div"><view class="el-div"><NativeText class="eyebrow dark el-span">家族档案</NativeText><view class="el-h2" id="memberDialogTitle">{{ editingId ? '编辑家人' : '录入家人' }}</view></view><NativeButton @click.stop="closeDialog()" aria-label="关闭" class="icon-btn el-button" data-close-dialog=""><NativeText class="ph ph-x el-i"></NativeText></NativeButton></view>
<view class="form-grid el-div">
<view class="el-label"><NativeText class="el-span">中文姓名</NativeText><NativeField @confirm="submitMember()" class="el-input" maxlength="12" name="name" placeholder="例如：江守诚" required="" v-model="memberForm.name"/></view>
<view class="el-label"><NativeText class="el-span">与我的关系</NativeText><NativeField :options="relationOptions" class="el-select" kind="select" name="relation" required="" v-model="memberForm.relation"/></view>
<view class="el-label"><NativeText class="el-span">性别</NativeText><NativeField :options="[{value:'未知',label:'未知'},{value:'男',label:'男'},{value:'女',label:'女'}]" class="el-select" kind="select" v-model="memberForm.gender"/></view>
<view class="el-label"><NativeText class="el-span">世代（1–100）</NativeText><NativeField class="el-input" type="number" min="1" max="100" v-model="memberForm.generation"/></view>
<view class="el-label"><NativeText class="el-span">公历出生日期</NativeText><NativeField @confirm="submitMember()" class="el-input" id="memberBirthday" name="birthday" type="date" v-model="memberForm.birthday"/></view>
<view class="el-label"><NativeText class="el-span">农历日期（自动换算）</NativeText><NativeField :model-value="memberLunar" @confirm="submitMember()" aria-live="polite" class="el-input" id="memberLunarBirthday" name="lunarBirthday" placeholder="选择公历日期后自动显示" readonly="" type="text"/></view>
<view class="el-label"><NativeText class="el-span">卒年（公历，可选）（如果没有详细信息）</NativeText><NativeField @confirm="submitMember()" class="el-input" inputmode="numeric" max="2100" min="1000" name="deathYear" placeholder="例如：2018" type="number" v-model="memberForm.deathYear"/></view>
<view class="el-label"><NativeText class="el-span">具体忌日（公历，可选）</NativeText><NativeField class="el-input" type="date" v-model="memberForm.deathDate"/><NativeText class="form-hint">填写后以此日期的年份作为卒年。</NativeText></view>
<view class="el-label"><NativeText class="el-span">头像显示文字（可选）</NativeText><NativeField @confirm="submitMember()" class="el-input" maxlength="2" name="avatarLabel" placeholder="默认显示姓名末字" v-model="memberForm.avatarLabel"/></view>
<view class="el-label"><NativeText class="el-span">头像名称说明（可选）</NativeText><NativeField @confirm="submitMember()" class="el-input" maxlength="12" name="avatarName" placeholder="例如：父亲、祖父" v-model="memberForm.avatarName"/></view>
<view class="full-field el-label"><NativeText class="el-span">生平简介</NativeText><NativeField @confirm="submitMember()" class="el-textarea" kind="textarea" maxlength="2000" name="bio" placeholder="记录籍贯、经历或想要留存的故事" rows="3" v-model="memberForm.bio"></NativeField></view>
</view>
<view class="member-relations el-section">
<view class="member-relations-heading"><NativeText class="el-strong">人物关联</NativeText><NativeText class="form-hint">选择已录入的家人，建立家谱连线与亲属关系。</NativeText></view>
<view class="form-grid">
<view class="el-label"><NativeText class="el-span">父亲</NativeText><NativeField :disabled="saveBusy" :options="relatedMemberOptions" class="el-select" id="memberFather" name="fatherId" kind="select" v-model="memberForm.parentOne"/></view>
<view class="el-label"><NativeText class="el-span">母亲</NativeText><NativeField :disabled="saveBusy" :options="relatedMemberOptions" class="el-select" id="memberMother" name="motherId" kind="select" v-model="memberForm.parentTwo"/></view>
<view class="full-field el-label"><NativeText class="el-span">配偶</NativeText><NativeField :disabled="saveBusy" :options="relatedMemberOptions" class="el-select" id="memberSpouse" name="spouseId" kind="select" v-model="memberForm.spouseId"/></view>
</view>
<view v-if="formRelations.length" class="member-relations-preview" aria-live="polite"><NativeText v-for="link in formRelations" :key="link.role" class="el-span">{{ link.role }}：{{ link.label }}</NativeText></view>
<view v-else class="form-hint">尚未关联人物。可先保存成员，再回来补充；家人尚未录入时请先录入家人。</view>
</view>
<view class="check-row el-label"><NativeField @confirm="submitMember()" class="el-input" name="deceased" type="checkbox" v-model="memberForm.deceased"/><NativeText @click="memberForm.deceased = !memberForm.deceased" class="el-span">该成员已故</NativeText></view>
<view class="check-row el-label"><NativeField type="checkbox" v-model="memberForm.createBirthdayReminder"/><NativeText @click="memberForm.createBirthdayReminder = !memberForm.createBirthdayReminder">同时创建或更新生日提醒</NativeText></view>
<view class="check-row el-label"><NativeField type="checkbox" v-model="memberForm.createMemorialReminder"/><NativeText @click="memberForm.createMemorialReminder = !memberForm.createMemorialReminder">同时创建或更新忌日提醒（须填写具体忌日）</NativeText></view>
<view class="form-hint">世代用于家谱排版。</view>
<view class="dialog-actions el-div"><NativeButton :disabled="saveBusy" @click.stop="closeDialog()" class="btn btn-secondary el-button" data-close-dialog="">取消</NativeButton><NativeButton :disabled="saveBusy || !canEdit" @click.stop="submitMember()" class="btn btn-primary el-button" id="saveMember">{{ saveBusy ? '保存中…' : '保存成员' }}</NativeButton></view>
</NativeForm>
</view></view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'profileDialog'"><view @click.stop aria-modal="true" class="app-dialog profile-dialog el-dialog" id="profileDialog" role="dialog" v-if="dialog === 'profileDialog'">
<NativeForm class="el-form" id="profileForm">
<view class="dialog-header el-div"><view class="el-div"><NativeText class="eyebrow dark el-span">账户资料</NativeText><view class="el-h2">自定义头像与名称</view></view><NativeButton @click="closeDialog()" aria-label="关闭" class="icon-btn el-button" data-close-dialog=""><NativeText class="ph ph-x el-i"></NativeText></NativeButton></view>
<view class="profile-editor el-div">
<view class="profile-avatar-editor el-div">
<NativeText :class="{ 'has-image': !!profileForm.avatar }" :style="avatarStyle(profileForm.avatar)" aria-label="头像预览" class="avatar avatar-text profile-avatar-preview el-span" id="profileAvatarPreview">{{ profileForm.avatar ? '' : accountAvatarText(profileForm.name) }}</NativeText>
<view class="el-div"><NativeButton :disabled="avatarBusy || saveBusy" @click="chooseAvatar()" class="btn btn-secondary btn-small el-label"><NativeText class="ph ph-image el-i"></NativeText>{{ avatarBusy ? '上传中…' : '选择头像' }}</NativeButton><NativeButton :disabled="avatarBusy || saveBusy" @click="profileForm.avatar = ''" class="text-btn profile-avatar-reset el-button" id="resetProfileAvatar">恢复默认</NativeButton><NativeText class="el-small">支持 JPG、PNG、WEBP，最大 2MB</NativeText></view>
</view>
<view class="profile-name-field el-label"><NativeText class="el-span">家族名称</NativeText><NativeField @confirm="submitProfile()" class="el-input" id="profileNameInput" maxlength="20" name="profileName" placeholder="例如：江氏家族" required="" v-model="profileForm.name"/></view>
</view>
<view class="dialog-actions el-div"><NativeButton @click="closeDialog()" class="btn btn-secondary el-button" data-close-dialog="">取消</NativeButton><NativeButton :disabled="saveBusy || avatarBusy || !canEdit" @click="submitProfile()" class="btn btn-primary el-button" id="saveProfile"><NativeText class="ph ph-check el-i"></NativeText>{{ saveBusy ? '保存中…' : '保存资料' }}</NativeButton></view>
</NativeForm>
</view></view>
<view @click.self="closeDialog()" class="modal-layer login-layer" v-if="dialog === 'loginDialog'"><view :class="{ 'is-required': !store.session }" @click.stop aria-describedby="loginPrivacyNote" aria-labelledby="loginHeading" aria-modal="true" class="app-dialog login-dialog el-dialog" id="loginDialog" role="dialog" v-if="dialog === 'loginDialog'">
<NativeForm class="el-form" id="loginForm">
<view aria-label="家谱制作器介绍" class="login-story el-section">
<view class="login-brand el-div"><NativeText aria-hidden="true" class="login-brand-mark el-span">谱</NativeText><NativeText class="el-span"><NativeText class="el-strong">家谱制作器</NativeText><NativeText class="el-small">宗谱档案管理</NativeText></NativeText></view>
<view class="login-story-copy el-div"><NativeText class="login-kicker el-span">我的家谱 · 数字典藏</NativeText><view class="el-h2">一页家谱，<NativeText class="el-br">{{ '\n' }}</NativeText>续写百年家史。</view><view class="el-p">整理世系，记录生平与重要日子，让家族记忆有迹可循。</view></view>
<view aria-hidden="true" class="login-lineage el-div"><NativeText class="el-span"></NativeText><NativeText class="el-i"></NativeText><NativeText class="el-i"></NativeText><NativeText class="el-i"></NativeText></view>
<view aria-hidden="true" class="login-seal el-div"><NativeText class="el-span">敬宗</NativeText><NativeText class="el-span">睦族</NativeText></view>
</view>
<view class="login-panel el-section">
<NativeButton @click="closeDialog()" aria-label="关闭" class="icon-btn login-dismiss login-close el-button" data-close-dialog=""><NativeText class="ph ph-x el-i"></NativeText></NativeButton>
<view class="login-heading el-header"><NativeText class="el-span">{{ loginForm.mode === 'register' ? '初次见面' : loginForm.mode === 'forgot' ? '找回账号' : '欢迎回来' }}</NativeText><view class="el-h2" id="loginHeading">{{ loginForm.mode === 'register' ? '创建家谱账号' : loginForm.mode === 'forgot' ? '重置密码' : '进入家谱' }}</view><view class="el-p">{{ loginForm.mode === 'register' ? '手机号已验证，设置账号和密码即可开始。' : loginForm.mode === 'forgot' ? '使用绑定的手机号找回密码。' : '输入手机号或账号，开始记录家族故事。' }}</view></view>
<view class="login-fields el-div">
<view v-if="loginForm.mode === 'login'" class="el-label"><NativeText class="el-span">手机号或账号</NativeText><view class="login-input el-span"><NativeText :class="loginMethod === 'phone' ? 'ph-device-mobile' : 'ph-user'" class="ph el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" autocomplete="username" autocapitalize="none" :spellcheck="false" class="el-input" id="loginIdentifier" maxlength="32" name="identifier" placeholder="请输入手机号或账号" required="" v-model="loginForm.identifier"/></view></view>
<view v-if="loginForm.mode === 'register'" class="el-label"><NativeText class="el-span">已验证手机号</NativeText><view class="login-verified-phone"><NativeText class="el-span">{{ maskedLoginPhone }}</NativeText><NativeButton :disabled="loginBusy || smsSending" @click="setLoginMode('login')" class="text-btn el-button">更换手机号</NativeButton></view></view>
<view v-if="loginForm.mode === 'register'" class="el-label"><NativeText class="el-span">账号</NativeText><view class="login-input el-span"><NativeText class="ph ph-user el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" @update:model-value="loginError = ''" autocomplete="username" class="el-input" id="loginUsername" maxlength="32" name="username" placeholder="设置登录账号" required="" v-model="loginForm.username"/></view></view>
<view v-if="loginForm.mode === 'forgot'" class="el-label"><NativeText class="el-span">手机号</NativeText><view class="login-input el-span"><NativeText class="ph ph-device-mobile el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" autocomplete="tel" class="el-input" id="loginPhone" maxlength="11" name="phone" placeholder="请输入绑定的 11 位手机号" type="tel" required="" v-model="loginForm.phone"/></view></view>
<view v-if="(loginForm.mode === 'login' && loginMethod === 'phone') || loginForm.mode === 'forgot' || (loginForm.mode === 'register' && !loginForm.registrationToken)" class="el-label"><NativeText class="el-span">短信验证码</NativeText><view class="sms-input-row el-span"><view class="login-input"><NativeText class="ph ph-shield-check el-i"></NativeText><NativeField :disabled="loginBusy || smsSending" @confirm="submitLogin()" @update:model-value="loginError = ''" autocomplete="one-time-code" class="el-input" id="loginSmsCode" maxlength="6" name="smsCode" placeholder="请输入 6 位验证码" type="tel" required="" v-model="loginForm.smsCode"/></view><NativeButton :disabled="loginBusy || smsSending || !!smsCountdown || (loginForm.mode !== 'forgot' && !loginForm.acceptedTerms)" @click="sendLoginSms()" class="btn btn-secondary sms-button el-button">{{ smsSending ? '发送中…' : smsCountdown ? smsCountdown + ' 秒' : '发送验证码' }}</NativeButton></view></view>
<view v-if="(loginForm.mode === 'login' && loginMethod === 'account') || loginForm.mode === 'register'" class="el-label"><NativeText class="el-span">密码</NativeText><view class="login-input el-span"><NativeText class="ph ph-lock-key el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" @update:model-value="loginError = ''" :autocomplete="loginForm.mode === 'register' ? 'new-password' : 'current-password'" class="el-input" id="loginPassword" maxlength="64" minlength="6" type="password" v-model="loginForm.password" :placeholder="loginForm.mode === 'register' ? '设置 6 至 64 位密码' : '请输入密码'"/></view></view>
<view v-if="loginForm.mode === 'register'" class="el-label"><NativeText class="el-span">确认密码</NativeText><view class="login-input el-span"><NativeText class="ph ph-lock-key el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" @update:model-value="loginError = ''" autocomplete="new-password" class="el-input" maxlength="64" type="password" v-model="loginForm.passwordConfirm" placeholder="请再次输入密码"/></view></view>
<view v-if="loginForm.mode === 'forgot'" class="el-label"><NativeText class="el-span">新密码</NativeText><view class="login-input el-span"><NativeText class="ph ph-lock-key el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" autocomplete="new-password" class="el-input" maxlength="64" type="password" v-model="loginForm.newPassword" placeholder="请输入新密码"/></view></view>
<view v-if="loginForm.mode === 'forgot'" class="el-label"><NativeText class="el-span">确认新密码</NativeText><view class="login-input el-span"><NativeText class="ph ph-lock-key el-i"></NativeText><NativeField :disabled="loginBusy" @confirm="submitLogin()" autocomplete="new-password" class="el-input" maxlength="64" type="password" v-model="loginForm.newPasswordConfirm" placeholder="请再次输入新密码"/></view></view>
</view>
<view v-if="loginForm.mode !== 'forgot'" class="check-row login-agreement el-label">
<NativeField :disabled="loginBusy" aria-label="同意免责声明和使用规范" aria-describedby="loginAgreementNote" class="el-input" id="acceptedTerms" name="acceptedTerms" type="checkbox" v-model="loginForm.acceptedTerms"/>
<view class="login-agreement-copy"><NativeText @click="!loginBusy && (loginForm.acceptedTerms = !loginForm.acceptedTerms)" class="el-span">我已阅读并同意</NativeText><NativeButton :disabled="loginBusy" @click="openLegal('disclaimer')" class="text-btn legal-link el-button">《免责声明》</NativeButton><NativeText class="el-span">和</NativeText><NativeButton :disabled="loginBusy" @click="openLegal('rules')" class="text-btn legal-link el-button">《使用规范》</NativeButton></view>
</view>
<view v-if="loginForm.mode !== 'forgot'" class="login-register-hint el-p" id="loginAgreementNote">请特别阅读辱骂与网暴规则、责任划分、资料授权和个人信息条款；同意后方可登录或注册。</view>
<view v-if="loginForm.mode !== 'forgot'" class="check-row login-remember el-label"><NativeField :disabled="loginBusy" class="el-input" name="remember" type="checkbox" v-model="loginForm.remember"/><NativeText @click="!loginBusy && (loginForm.remember = !loginForm.remember)" class="el-span">在此设备保持登录</NativeText></view>
<view v-if="loginForm.mode !== 'forgot'" class="login-register-hint el-p">{{ loginForm.remember ? '下次在此设备打开时自动登录。' : '关闭后需重新登录。' }}</view>
<view class="login-error el-p" id="loginError" role="alert" v-if="loginError">{{ loginError }}</view>
<NativeButton :disabled="loginBusy || smsSending || (loginForm.mode !== 'forgot' && !loginForm.acceptedTerms)" @click="submitLogin()" class="btn btn-primary login-submit el-button" id="submitLogin"><NativeText class="el-span">{{ loginBusy ? '请稍候…' : smsSending ? '发送验证码中…' : loginForm.mode === 'register' ? '创建账号并登录' : loginForm.mode === 'forgot' ? '重置密码' : loginMethod === 'phone' ? '验证并继续' : loginMethod === 'account' ? '登录' : '继续' }}</NativeText><NativeText class="ph ph-arrow-right el-i"></NativeText></NativeButton>
<NativeButton v-if="loginForm.mode === 'login'" :disabled="loginBusy || smsSending" @click="enterGuestMode()" class="btn btn-secondary guest-entry el-button"><NativeText class="ph ph-eye el-i"></NativeText>我是访客，先浏览</NativeButton>
<NativeButton :disabled="loginBusy || smsSending" class="btn forgot-entry el-button" @click="setLoginMode(loginForm.mode === 'login' ? 'forgot' : 'login')">{{ loginForm.mode === 'login' ? '忘记密码' : '返回登录' }}</NativeButton>
<view class="login-register-hint el-p" aria-live="polite">{{ loginForm.mode === 'register' ? '新用户完成账号设置后即可进入家谱。' : loginForm.mode === 'forgot' ? '使用手机号和短信验证码重置密码。' : loginMethod === 'phone' ? '同意条款后自动发送验证码；新手机号验证后进入账号设置。' : loginMethod === 'account' ? '请输入此账号的登录密码。' : '手机号使用短信验证码，账号使用密码。' }}</view>
<view class="login-register-hint el-p">手机号验证后可用亲友提供的 6 位家族邀请码加入家谱；没有邀请码也可进入自己的家谱。邀请码与短信验证码不同。</view>
<view class="login-note el-p" id="loginPrivacyNote"><NativeText class="ph ph-shield-check el-i"></NativeText><NativeText class="el-span">账号密码保存在服务端数据库，密码经过单向加密，不保存明文。</NativeText></view>
</view>
</NativeForm>
</view></view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'reminderDialog'"><view @click.stop aria-modal="true" class="app-dialog el-dialog" id="reminderDialog" role="dialog" v-if="dialog === 'reminderDialog'">
<NativeForm class="el-form" id="reminderForm">
<view class="dialog-header el-div"><view class="el-div"><NativeText class="eyebrow dark el-span">重要日子</NativeText><view class="el-h2">{{ reminderForm.id ? '编辑提醒' : '新建提醒' }}</view></view><NativeButton @click="closeDialog()" aria-label="关闭" class="icon-btn el-button" data-close-dialog=""><NativeText class="ph ph-x el-i"></NativeText></NativeButton></view>
<view class="form-grid el-div">
<view class="el-label"><NativeText class="el-span">提醒名称</NativeText><NativeField @confirm="submitReminder()" class="el-input" maxlength="20" name="title" placeholder="例如：母亲生日" required="" v-model="reminderForm.title"/></view>
<view class="el-label"><NativeText class="el-span">提醒类型</NativeText><NativeField :options='[{"value": "birthday", "label": "生日"}, {"value": "memorial", "label": "忌日"}, {"value": "festival", "label": "传统祭日"}]' @confirm="submitReminder()" class="el-select" kind="select" name="type" required="" v-model="reminderForm.type"></NativeField></view>
<view class="reminder-member-field el-label"><NativeText class="el-span">相关人员（仅限已录入族谱成员）</NativeText><NativeField :disabled="saveBusy || /^auto-(birthday|memorial)-/.test(reminderForm.id)" :options="reminderMemberOptions" @confirm="submitReminder()" class="el-select" id="reminderMember" kind="select" name="memberId" v-model="reminderForm.memberId"></NativeField><NativeText v-if="/^auto-(birthday|memorial)-/.test(reminderForm.id)" class="form-hint">自动提醒关联来源成员，日期会随成员档案更新。其他成员请另建提醒。</NativeText></view>
<view class="el-label"><NativeText class="el-span">重复使用的历法</NativeText><NativeField :options="[{value:'solar',label:'公历同月日'},{value:'lunar',label:'农历同月日'},{value:'qingming',label:'清明节气（每年自动换算）'}]" kind="select" class="el-select" @change="setReminderCalendar" v-model="reminderForm.calendar_type"/></view>
<view class="el-label"><NativeText class="el-span">基准公历日期</NativeText><NativeField @confirm="submitReminder()" class="el-input" id="reminderDate" name="date" required="" type="date" v-model="reminderForm.date"/></view>
<view class="el-label"><NativeText class="el-span">农历日期（自动换算）</NativeText><NativeField :model-value="reminderLunar" @confirm="submitReminder()" aria-live="polite" class="el-input" id="reminderLunar" name="lunar" placeholder="选择公历日期后自动显示" readonly="" type="text"/></view>
<view class="el-label"><NativeText class="el-span">提前提醒</NativeText><NativeField :options='[{"value": "当天", "label": "当天"}, {"value": "提前1天", "label": "提前 1 天"}, {"value": "提前3天", "label": "提前 3 天"}, {"value": "提前7天", "label": "提前 7 天"}, {"value": "提前15天", "label": "提前 15 天"}]' @confirm="submitReminder()" class="el-select" kind="select" name="advance" v-model="reminderForm.advance"></NativeField></view>
<view class="el-label"><NativeText class="el-span">重复</NativeText><NativeField :options='[{"value": "每年", "label": "每年"}, {"value": "仅一次", "label": "仅一次"}]' @confirm="submitReminder()" class="el-select" kind="select" name="repeat" v-model="reminderForm.repeat"></NativeField></view>
</view>
<view class="form-hint">农历模式以基准日期换算出的农历月日重复；闰月与清明日期由历法计算。</view>
<view class="dialog-actions el-div"><NativeButton :disabled="saveBusy" @click="closeDialog()" class="btn btn-secondary el-button" data-close-dialog="">取消</NativeButton><NativeButton :disabled="saveBusy || !canEdit" @click="submitReminder()" class="btn btn-primary el-button" id="saveReminder">{{ saveBusy ? '保存中…' : '保存提醒' }}</NativeButton></view>
</NativeForm>
</view></view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'personDialog'"><view @click.stop aria-modal="true" class="app-dialog person-dialog el-dialog" id="personDialog" role="dialog" v-if="dialog === 'personDialog'">
<NativeForm class="el-form">
<view class="dialog-header el-div"><view class="el-div"><NativeText class="eyebrow dark el-span">成员档案</NativeText><view class="el-h2" id="personDialogName">{{ activeMember?.name }}</view></view><NativeButton @click.stop="closeDialog()" aria-label="关闭" class="icon-btn el-button" data-close-dialog=""><NativeText class="ph ph-x el-i"></NativeText></NativeButton></view>
<view class="person-summary el-div"><NativeText class="avatar avatar-text large el-span" id="personDialogAvatar">{{ activeMember?.avatarLabel || activeMember?.name.slice(-1) }}</NativeText><view class="el-div"><NativeText class="el-strong" id="personDialogRelation">{{ personInfo.relation }}</NativeText><view class="el-p" id="personDialogLifeYears">{{ personInfo.years }}</view></view></view>
<view class="person-record el-div">
<view class="el-section"><NativeText class="person-record-label el-span"><NativeText class="ph ph-calendar-blank el-i"></NativeText>生卒信息</NativeText><NativeText class="el-strong" id="personDialogLifespan">{{ personInfo.lifespan }}</NativeText><view class="el-p" id="personDialogBirthday">{{ personInfo.birthday }}</view></view>
<view class="el-section"><NativeText class="person-record-label el-span"><NativeText class="ph ph-scroll el-i"></NativeText>生平事迹</NativeText><view class="person-biography el-p" id="personDialogBio">{{ personInfo.bio }}</view></view>
<view class="el-section"><NativeText class="person-record-label el-span"><NativeText class="ph ph-git-branch el-i"></NativeText>人物关联</NativeText><view v-if="personRelations.length" class="person-relation-list"><NativeButton v-for="link in personRelations" :key="link.role + link.id" @click.stop="viewRelatedPerson(link.id)" class="person-relation-link el-button"><NativeText class="person-relation-role">{{ link.role }}</NativeText><NativeText class="person-relation-name">{{ link.label }}</NativeText><NativeText aria-hidden="true" class="ph ph-caret-right el-i"></NativeText></NativeButton></view><view v-else class="el-p">尚未关联人物，可在编辑资料中选择父亲、母亲或配偶。</view></view>
</view>
<view class="person-actions el-div"><NativeButton :disabled="!canEdit || saveBusy" @click.stop="removeActiveMember()" class="btn btn-danger el-button"><NativeText class="ph ph-trash el-i"></NativeText>删除成员</NativeButton><NativeButton :disabled="!canEdit" @click.stop="editActiveMember()" class="btn btn-secondary el-button" data-person-action="edit"><NativeText class="ph ph-pencil-simple el-i"></NativeText>编辑资料</NativeButton><NativeButton :disabled="!canEdit" @click.stop="remindActiveMember()" class="btn btn-primary el-button" data-person-action="reminder"><NativeText class="ph ph-calendar-plus el-i"></NativeText>设置提醒</NativeButton></view>
</NativeForm>
</view></view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'relationDialog'"><view @click.stop aria-modal="true" class="app-dialog relation-dialog el-dialog" id="relationDialog" role="dialog" v-if="dialog === 'relationDialog'">
<NativeForm class="el-form">
<view class="dialog-header el-div"><view class="el-div"><NativeText class="eyebrow dark el-span">关系分析</NativeText><view class="el-h2">两人关系结果</view></view><NativeButton @click="closeDialog()" aria-label="关闭" class="icon-btn el-button" data-close-dialog=""><NativeText class="ph ph-x el-i"></NativeText></NativeButton></view>
<view class="relation-dialog-summary el-div">
<NativeText class="avatar avatar-text el-span" id="relationDialogAvatarA">{{ (selectedMemberNames[0] || '甲').slice(-1) }}</NativeText><NativeText class="el-strong" id="relationDialogPersonA">{{ selectedLabels[0] || '第一人' }}</NativeText><NativeText aria-hidden="true" class="ph ph-git-branch el-i"></NativeText><NativeText class="avatar avatar-text el-span" id="relationDialogAvatarB">{{ (selectedMemberNames[1] || '乙').slice(-1) }}</NativeText><NativeText class="el-strong" id="relationDialogPersonB">{{ selectedLabels[1] || '第二人' }}</NativeText>
</view>
<RelationResult :result="dialogResult" dialog="" id="relationResult"></RelationResult>
<view class="dialog-actions el-div"><NativeButton @click="closeDialog()" class="btn btn-secondary el-button" data-close-dialog="">关闭</NativeButton><NativeButton @click="chooseAgain()" class="btn btn-primary el-button" id="relationChooseAgain"><NativeText class="ph ph-cursor-click el-i"></NativeText>重新选择两人</NativeButton></view>
</NativeForm>
</view></view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'familyGuide' && familyGuideMode"><FamilyGuide :mode="familyGuideMode" :busy="familyGuideBusy" :error="familyGuideError" @join="joinFromLogin" @personal="enterPersonalFromLogin" @dismiss="dismissGuide" @close="closeDialog" @reset="restoreGuide" @navigate="guideNavigate" /></view>
<view @click.self="closeDialog()" class="modal-layer" v-if="dialog === 'accountTools'"><AccountTools ref="accountTools" :initial-tab="toolsTab" @close="closeDialog" @signed-out="loginAction" /></view>
<view v-if="dialog === 'legalDialog'" @click.self="closeLegal()" class="modal-layer legal-layer">
<view @click.stop aria-modal="true" aria-labelledby="legalHeading" class="app-dialog legal-dialog" id="legalDialog" role="dialog">
<view class="dialog-header legal-header"><view><NativeText class="eyebrow dark el-span">服务条款 · {{ terms.version }}</NativeText><view class="el-h2" id="legalHeading">{{ activeLegalDocument.title }}</view><view class="legal-date el-p">生效日期：{{ terms.effectiveDate }}</view></view><NativeButton @click="closeLegal()" aria-label="关闭条款" class="icon-btn el-button"><NativeText class="ph ph-x el-i"></NativeText></NativeButton></view>
<scroll-view scroll-y class="legal-document-body"><view tabindex="0" role="region" :aria-label="activeLegalDocument.title + '正文'"><view v-for="section in activeLegalDocument.sections" :key="section.title" :class="{ 'legal-important': section.title.includes('重要') }" class="legal-section"><view class="el-h3">{{ section.title }}</view><view v-for="(paragraph, index) in section.paragraphs" :key="index" class="el-p">{{ paragraph }}</view></view></view></scroll-view>
<view class="legal-footer"><NativeText class="el-small">阅读或关闭条款不会自动勾选同意。</NativeText><NativeButton @click="closeLegal()" class="btn btn-secondary el-button">返回</NativeButton></view>
</view>
</view>
<view :class="{ show: toastState.show }" aria-live="polite" class="toast el-div" id="toast" role="status"><NativeText :class="toastState.icon" class="ph el-i"></NativeText><NativeText class="el-span">{{ toastState.message }}</NativeText></view>



</view>
</template>
<script setup>
// #ifdef H5
import NativeText from '../../components/parity/NativeText.h5.js'
import NativeButton from '../../components/parity/NativeButton.h5.js'
import NativeForm from '../../components/parity/NativeForm.h5.js'
// #endif
// #ifndef H5
import NativeText from '../../components/parity/NativeText.vue'
import NativeButton from '../../components/parity/NativeButton.vue'
import NativeForm from '../../components/parity/NativeForm.vue'
// #endif

import AccountTools from '../../components/parity/AccountTools.vue'
import FamilySharing from '../../components/parity/FamilySharing.vue'
import FamilyGuide from '../../components/parity/FamilyGuide.vue'
import FamilyTree from '../../components/parity/FamilyTree.vue'
import RelationResult from '../../components/parity/RelationResult.vue'
// #ifdef H5
import NativeField from '../../components/parity/NativeField.h5.js'
import NativeImage from '../../components/parity/NativeImage.h5.js'
// #endif
// #ifndef H5
import NativeField from '../../components/parity/NativeField.vue'
import NativeImage from '../../components/parity/NativeImage.vue'
// #endif
import { useParityPage } from '../../utils/parity-page.js'
import { computed } from 'vue'
import terms from '../../static/legal/terms.json'
const { legalDocument, openLegal, closeLegal, familySharing, familyGuideMode, familyGuideBusy, familyGuideError, openFamilyGuides, closeFamilyGuide, joinFromLogin, enterPersonalFromLogin, dismissGuide, restoreGuide, guideNavigate, formRelations, personRelations, viewRelatedPerson, store, accountTools, canEdit, saveBusy, avatarBusy, theme, setTheme, elderMode, setElderMode, toolsTab, openTools, unreadNotifications, syncLabel, conflictDetails, syncNow, resolveConflict, relationOptions, relatedMemberOptions, setReminderCalendar, editReminder, removeActiveMember, currentPage, pageTitles, todayLabel, generationCount, showPage, scrollMain, openDialog, closeDialog, avatarStyle, accountAvatarText, loginAction, enterGuestMode, editProfile, toast, clearDemo, treeView, search, filteredMembers, selectedNames, selectedMemberNames, selectedLabels, selecting, selectionNote, setTreeView, resetTree, startSelection, chooseAgain, pickPerson, demoMembers, userTree, demoTree, relationMode, relationNameA, relationNameB, relationYearA, relationYearB, memberNames, relationMemberOptions, homeResult, analyzeHome, calendarYear, calendarMonth, calendarLunarSummary, calendarCells, changeMonth, openReminderDate, upcomingReminders, homeReminders, nextFestival, timelineReminders, removeReminder, dialog, memberForm, editingId, memberLunar, submitMember, reminderForm, reminderLunar, reminderMemberOptions, loginForm, loginMethod, maskedLoginPhone, loginBusy, loginError, setLoginMode, sendLoginSms, smsCountdown, smsSending, submitLogin, profileForm, chooseAvatar, submitProfile, activeMember, personInfo, editActiveMember, remindActiveMember, dialogResult, toastState } = useParityPage()
const activeLegalDocument = computed(() => terms[legalDocument.value] || terms.disclaimer)
</script>
