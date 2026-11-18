<template>
  <div class="platforms-view">
    <div class="page-head"><div><div class="page-title">平台接入</div><div class="page-desc">管理各平台适配器、接入地址与出口代理</div></div><div class="head-actions"><button class="btn primary" @click="showForm = true">＋ 添加平台</button></div></div>
    <div v-loading="loading" class="platforms-body">
      <div class="plat-grid">
        <div v-for="p in items" :key="p.id" class="card plat">
          <div class="plat-top"><span class="dot" :class="{ warn: !p.enabled }"></span><span class="plat-name">{{ p.name }}</span><span class="chip" :class="p.enabled ? 'cn' : ''">{{ p.enabled ? '已启用' : '已停用' }}</span></div>
          <div class="plat-meta">适配器：<b>{{ p.adapter }}</b><template v-if="p.builtin"> · 内置</template></div>
          <code v-if="p.base_url" class="plat-code">{{ p.base_url }}</code><code v-if="p.proxy" class="plat-code">出口：{{ p.proxy }}</code>
          <div class="plat-stats"><div class="plat-stat"><b>{{ p.account_count || 0 }}</b><span>账号</span></div><div class="plat-stat"><b>{{ p.enabled ? '在线' : '停用' }}</b><span>状态</span></div></div>
          <div class="plat-actions"><button class="btn sm" :disabled="busy === p.id" @click="toggle(p)">{{ p.enabled ? '停用' : '启用' }}</button><button v-if="!p.builtin" class="btn sm danger" :disabled="busy === p.id" @click="doDelete(p)">删除</button></div>
        </div>
      </div>
      <div v-if="!items.length && !loading" class="card empty-state"><strong>暂无平台</strong><span>添加一个自定义平台开始接入</span></div>
    </div>
    <div v-if="showForm" class="mask open" @click.self="showForm = false"><div class="modal open platform-modal">
      <div class="modal-head"><span>添加自定义平台</span><button class="btn ghost icon" @click="showForm = false">×</button></div>
      <div class="modal-body"><div class="form-grid">
        <div class="field"><label>平台标识 key</label><input class="input" v-model="form.key" placeholder="如 my-provider" /></div><div class="field"><label>显示名称</label><input class="input" v-model="form.name" placeholder="如 我的转发" /></div>
        <div class="field"><label>适配器类型</label><select class="select" v-model="form.adapter"><option value="tabbit">tabbit（Tabbit 协议）</option><option value="loomy">loomy（Loomy 讯飞，OpenAI 兼容）</option><option value="openai_compat">openai_compat(OpenAI 兼容直连,如 workbuddy / trae 网关)</option><option value="custom" disabled>custom(待接入,后端未注册)</option><option value="trae" disabled>trae(待接入,后端未注册)</option><option value="workbuddy" disabled>workbuddy(待接入,后端未注册)</option></select></div><div class="field"><label>启用</label><select class="select" v-model="form.enabled"><option :value="1">是</option><option :value="0">否</option></select></div>
        <div class="field"><label>Base URL（API 地址）</label><input class="input" v-model="form.base_url" placeholder="https://api.example.com" /></div><div class="field"><label>出口代理（可选）</label><input class="input" v-model="form.proxy" placeholder="socks5h://127.0.0.1:1080" /><span class="hint">国际版服务必填出口代理，如 Tabbit 国际版走 1080</span></div>
      </div></div>
      <div class="modal-foot"><button class="btn" @click="showForm = false">取消</button><button class="btn primary" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button></div>
    </div></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getPlatforms, createPlatform, updatePlatform, deletePlatform } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const items = ref([])
const loading = ref(false)
const busy = ref(null)
const saving = ref(false)
const showForm = ref(false)
const form = ref({ key: '', name: '', adapter: 'tabbit', base_url: '', proxy: '', enabled: 1 })

const PLAT_LOGO = { 'tabbit-domestic': 'dom', 'tabbit-intl': 'intl', 'loomy': 'loomy', 'trae': 'trae', 'workbuddy': 'work' }
const logoClass = (key) => PLAT_LOGO[key] || 'generic'
const logoText = (key) => (key.startsWith('tabbit') ? 'TB' : key === 'loomy' ? 'L' : key === 'trae' ? 'T' : key === 'workbuddy' ? 'W' : key.slice(0, 2).toUpperCase())

async function load() {
  loading.value = true
  try {
    const r = await getPlatforms()
    items.value = r.items
  } catch (e) {
    toastErr('加载平台失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function save() {
  const f = form.value
  if (!f.key.trim() || !f.name.trim()) return toastErr('请填写平台标识与显示名称')
  saving.value = true
  try {
    await createPlatform({ key: f.key.trim(), name: f.name.trim(), adapter: f.adapter, base_url: f.base_url.trim(), proxy: f.proxy.trim(), enabled: !!f.enabled, meta: {} })
    toastOk('平台已添加')
    showForm.value = false
    form.value = { key: '', name: '', adapter: 'tabbit', base_url: '', proxy: '', enabled: 1 }
    await load()
  } catch (e) {
    toastErr('添加失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function toggle(p) {
  busy.value = p.id
  try {
    await updatePlatform(p.id, { enabled: !p.enabled })
    toastOk(`平台「${p.name}」已${p.enabled ? '停用' : '启用'}`)
    await load()
  } catch (e) {
    toastErr('操作失败：' + (e.response?.data?.detail || e.message))
  } finally {
    busy.value = null
  }
}

async function doDelete(p) {
  try {
    await ElMessageBox.confirm(`确认删除平台「${p.name}」？其下账号将一并删除。`, '删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deletePlatform(p.id)
    toastOk('平台已删除')
    await load()
  } catch (e) {
    toastErr('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>

<style scoped>
.platforms-body { min-height: 160px; }
.plat-meta { margin-top: 12px; color: var(--text-2); font-size: 12px; }
.plat-code { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 7px; color: var(--text-3); font-size: 11px; }
.plat-actions { display: flex; gap: 7px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 34px 16px; color: var(--text-3); }
.empty-state strong { color: var(--text-2); font-size: 13px; }
.platform-modal { width: min(540px, calc(100vw - 32px)); }
.platform-modal .btn.icon { margin-left: auto; font-size: 20px; line-height: 1; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.form-grid .field { min-width: 0; }
@media (max-width: 560px) { .form-grid { grid-template-columns: 1fr; } }
</style>