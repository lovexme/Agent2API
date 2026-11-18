<template>
  <div class="shell">
    <!-- 侧栏 -->
    <aside class="sidebar" :class="{ open: drawer }">
      <div class="brand">
        <div class="brand-logo">A</div>
        <div class="brand-text">
          <div class="brand-name">AAM 聚合面板</div>
          <div class="brand-sub">AI Account Hub</div>
        </div>
      </div>

      <nav class="nav">
        <div v-for="group in navGroups" :key="group.label" class="nav-group">
          <div class="nav-group-label">{{ group.label }}</div>
          <router-link v-for="item in group.items" :key="item.path" :to="item.path" custom v-slot="{ navigate, isActive }">
            <div class="nav-item" :class="{ active: isActive }" :title="item.title" @click="navigate(); drawer = false">
              <span class="ico" v-html="item.icon"></span><span class="txt">{{ item.title }}</span>
              <span v-if="item.count != null" class="nav-count">{{ item.count }}</span>
            </div>
          </router-link>
        </div>
      </nav>

      <div class="sidebar-foot">
        <span class="dot" :class="{ err: !online }"></span>
        <span class="txt">{{ statusLabel }}</span>
        <span class="mono muted" style="margin-left:auto; font-size:10.5px">{{ hostLabel }}</span>
      </div>
    </aside>

    <!-- 移动端抽屉遮罩：点击任意外部区域收起 -->
    <div v-if="drawer" class="drawer-mask" @click="drawer = false"></div>

    <!-- 主区 -->
    <div class="main">
      <header class="topbar">
        <button class="btn ghost icon burger" @click="drawer = !drawer">☰</button>
        <div class="crumbs"><span>AAM</span> <span>/</span> <b>{{ currentTitle }}</b></div>
        <div class="topbar-actions">
          <span class="pill"><span class="dot" :class="{ err: !online }"></span>
            {{ statusLabel }} · {{ hostLabel }}
          </span>
          <div class="theme-switch">
            <button :class="{ on: theme === 'system' }" @click="applyTheme('system')">System</button>
            <button :class="{ on: theme === 'light' }" @click="applyTheme('light')">Light</button>
            <button :class="{ on: theme === 'dark' }" @click="applyTheme('dark')">Dark</button>
          </div>
          <button v-if="auth.authed" class="btn sm" @click="doLogout">退出</button>
        </div>
      </header>

      <div class="content">
        <router-view />
      </div>
    </div>

    <!-- 登录门 -->
    <div v-if="auth.needLogin" class="auth-gate">
      <div class="auth-card">
        <div class="auth-brand">
          <span class="brandmark">A</span>
          <h2>AAM 聚合面板</h2>
        </div>
        <p class="muted">AI 账号统一管理 · 管理接口已启用面板密钥保护，请输入密钥进入</p>
        <form @submit.prevent="doLogin">
          <input v-model="auth.key" type="password" placeholder="面板密钥（panel key）" autocomplete="off" autofocus />
          <button class="btn primary" type="submit" :disabled="auth.loading">{{ auth.loading ? '验证中…' : '进入面板' }}</button>
        </form>
        <p v-if="auth.error" class="auth-err">{{ auth.error }}</p>
        <p class="muted hint">密钥在服务器 data/admin_key.txt 中</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getOverview, getAdminMe, adminLogin, adminLogout } from './api'

const route = useRoute()
const online = ref(true)
const drawer = ref(false)

// ── 主题（system / light / dark，持久化）──
const theme = ref(localStorage.getItem('aam-theme') || 'light')
function applyTheme(mode) {
  theme.value = mode
  localStorage.setItem('aam-theme', mode)
  const dark = mode === 'dark' || (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}
applyTheme(theme.value)

// ── 面板鉴权门 ────────────────
const auth = reactive({ authed: false, needLogin: false, checking: true, key: '', error: '', loading: false })
async function checkAdmin() {
  auth.checking = true
  try {
    const me = await getAdminMe()
    auth.authed = !!me.authed
    auth.needLogin = !me.authed
  } catch {
    auth.authed = false
    auth.needLogin = true
  } finally {
    auth.checking = false
  }
}
async function doLogin() {
  if (!auth.key.trim()) return
  auth.loading = true
  auth.error = ''
  try {
    await adminLogin(auth.key.trim())
    auth.authed = true
    auth.needLogin = false
    window.location.reload()
  } catch (e) {
    auth.error = e.response?.data?.detail || '面板密钥错误'
  } finally {
    auth.loading = false
  }
}
async function doLogout() {
  try { await adminLogout() } catch {}
  window.location.reload()
}

const iconDash = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="11" width="7" height="10" rx="1.5"/><rect x="3" y="14" width="8" height="7" rx="1.5"/></svg>'
const iconAcct = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="9" cy="8" r="4"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M17 4a4 4 0 0 1 0 8m2 3a6 6 0 0 1 3 5v1"/></svg>'
const iconPlat = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v6"/></svg>'
const iconGw = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7h16M4 12h9M4 17h16"/><circle cx="17" cy="12" r="2"/></svg>'
const iconKey = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m2 2 2-2m-5 5 2-2"/></svg>'
const iconSet = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>'
const iconTask = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M8 11l2.5 2.5L16 8"/><path d="M3 8h18"/></svg>'
const iconLog = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 6h16M4 12h16M4 18h10"/></svg>'
const iconProxy = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 3v18M4 7.5l8 4.5 8-4.5"/></svg>'
const iconTool = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.8-.9-.9-2.8 2.6-2.6z"/></svg>'
const iconReport = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/></svg>'
const iconChat = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z"/><path d="M8 9h8M8 13h5"/></svg>'

const navGroups = [
  { label: '概览', items: [
    { path: '/', title: '总览', icon: iconDash },
    { path: '/report', title: '报表', icon: iconReport },
    { path: '/assistant', title: 'AI 助手', icon: iconChat },
  ] },
  { label: '账号池', items: [
    { path: '/accounts', title: '账号池', icon: iconAcct },
    { path: '/platforms', title: '平台健康', icon: iconPlat },
    { path: '/tasks', title: '每日任务', icon: iconTask },
  ] },
  { label: '网关', items: [
    { path: '/gateway', title: '模型路由', icon: iconGw },
    { path: '/proxies', title: '网络代理', icon: iconProxy },
    { path: '/services', title: '工具服务', icon: iconTool },
    { path: '/tokens', title: 'API 密钥', icon: iconKey },
    { path: '/requests', title: '请求日志', icon: iconLog },
  ] },
  { label: '系统', items: [{ path: '/settings', title: '设置', icon: iconSet }] },
]

const currentTitle = computed(() => route.meta?.title || '总览')
const hostLabel = computed(() => window.location.host)
const statusLabel = computed(() => {
  if (!online.value) return '后端离线'
  return auth.authed ? 'Gateway running' : '未登录'
})

// 移动端抽屉：路由切换 / ESC / 点击遮罩都收起
watch(() => route.path, () => { drawer.value = false })
function onKeydown(e) { if (e.key === 'Escape') drawer.value = false }

onMounted(async () => {
  checkAdmin()
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('aam:unauthorized', () => { auth.needLogin = true; auth.authed = false })
  const probe = async () => {
    try {
      await getOverview()
      online.value = true
    } catch (e) {
      // 401 = 服务在线但未登录（授权门拦截），不能算作“后端离线”
      online.value = e?.response?.status === 401
    }
  }
  probe()
  setInterval(probe, 60000)
})
</script>

<style scoped>
.nav-item .ico :deep(svg) { width: 15px; height: 15px; display: block; }
/* 移动端抽屉遮罩（桌面不显示） */
.drawer-mask { display: none; }
@media (max-width: 767px) {
  .drawer-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 70;
    background: rgba(0, 0, 0, .42);
    backdrop-filter: blur(1px);
  }
}
</style>
