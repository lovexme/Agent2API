<template>
  <div class="shell">
    <aside class="rail">
      <div class="brand">
        <span class="brandmark">A</span>
        <span>AAM<small>AI 账号聚合</small></span>
      </div>

      <div class="nav-label">工作台</div>
      <nav class="nav">
        <router-link v-for="item in navMain" :key="item.path" :to="item.path" custom v-slot="{ navigate, isActive }">
          <button class="nav-item" :class="{ active: isActive }" :title="item.title" @click="navigate">
            <span v-html="item.icon"></span><span>{{ item.title }}</span>
          </button>
        </router-link>
      </nav>

      <div class="nav-label">系统</div>
      <nav class="nav">
        <router-link v-for="item in navSystem" :key="item.path" :to="item.path" custom v-slot="{ navigate, isActive }">
          <button class="nav-item" :class="{ active: isActive }" :title="item.title" @click="navigate">
            <span v-html="item.icon"></span><span>{{ item.title }}</span>
          </button>
        </router-link>
      </nav>

      <div class="rail-foot">
        <span class="online" :class="{ off: !online }"></span>{{ online ? '网关运行中' : '后端离线' }}<br />
        <span style="padding-left: 14px">{{ hostLabel }}</span>
      </div>
    </aside>

    <main class="main">
      <header class="top">
        <div class="crumb">工作台 / <b>{{ currentTitle }}</b></div>
        <div class="top-right">
          <span>{{ isIPv6 ? 'IPv6 访问' : '本地访问' }}</span>
          <button v-if="auth.authed" class="btn secondary sm" style="margin-left:8px" @click="doLogout">退出</button>
          <span class="avatar">AAM</span>
        </div>
      </header>
      <router-view />
    </main>

    <div v-if="auth.needLogin" class="auth-gate">
      <div class="auth-card">
        <div class="auth-brand">
          <span class="brandmark">A</span>
          <h2>AAM 面板</h2>
        </div>
        <p class="muted">管理接口已启用面板密钥保护，请输入密钥进入</p>
        <form @submit.prevent="doLogin">
          <input v-model="auth.key" type="password" placeholder="面板密钥（panel key）" autocomplete="off" autofocus />
          <button class="btn" type="submit" :disabled="auth.loading">{{ auth.loading ? '验证中…' : '进入面板' }}</button>
        </form>
        <p v-if="auth.error" class="auth-err">{{ auth.error }}</p>
        <p class="muted hint">密钥在服务器 data/admin_key.txt 中</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getOverview, getAdminMe, adminLogin, adminLogout } from './api'

const route = useRoute()
const online = ref(true)

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

const iconDash = '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="11" width="7" height="10" rx="1"/><rect x="3" y="14" width="8" height="7" rx="1"/></svg>'
const iconAcct = '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="4"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M17 4a4 4 0 0 1 0 8m2 3a6 6 0 0 1 3 5v1"/></svg>'
const iconPlat = '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v6"/></svg>'
const iconGw = '<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h9M4 17h16"/><circle cx="17" cy="12" r="2"/></svg>'
const iconKey = '<svg viewBox="0 0 24 24"><path d="M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m2 2 2-2m-5 5 2-2"/></svg>'
const iconSet = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>'

const navMain = [
  { path: '/', title: '总览', icon: iconDash },
  { path: '/accounts', title: '账号管理', icon: iconAcct },
  { path: '/platforms', title: '平台接入', icon: iconPlat },
  { path: '/gateway', title: '统一网关', icon: iconGw },
  { path: '/tokens', title: 'API 密钥', icon: iconKey },
]
const navSystem = [{ path: '/settings', title: '设置', icon: iconSet }]

const currentTitle = computed(() => route.meta?.title || '总览')
const hostLabel = computed(() => window.location.host)
const isIPv6 = computed(() => window.location.hostname.includes(':'))

onMounted(async () => {
  checkAdmin()
  window.addEventListener('aam:unauthorized', () => { auth.needLogin = true; auth.authed = false })
  try {
    await getOverview()
    online.value = true
  } catch {
    online.value = false
  }
  setInterval(async () => {
    try {
      await getOverview()
      online.value = true
    } catch {
      online.value = false
    }
  }, 60000)
})
</script>

<style scoped>
.auth-gate {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 14, 18, 0.88);
  backdrop-filter: blur(6px);
}
.auth-card {
  width: 340px;
  padding: 28px 26px 22px;
  border: 1px solid var(--line, rgba(255, 255, 255, 0.12));
  border-radius: 14px;
  background: #12181f;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.45);
}
.auth-brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 6px;
}
.auth-brand h2 { margin: 0; font-size: 18px; }
.auth-card form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}
.auth-card input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--line, rgba(255, 255, 255, 0.15));
  background: #0d1216;
  color: var(--text, #e6eee9);
}
.auth-err { color: #ff7b7b; font-size: 12px; margin: 10px 0 0; }
.auth-card .hint { font-size: 11px; margin-top: 12px; text-align: center; }
</style>