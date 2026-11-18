<template>
  <div class="view-wrap">
    <div class="page-head">
      <div><div class="page-title">网络代理</div><div class="page-desc">平台级出口代理管理 · 连通性测试</div></div>
      <div class="head-actions"><button class="btn primary" type="button" :disabled="testingAll || !items.length" @click="testAll">{{ testingAll ? '测试中...' : '测试全部' }}</button></div>
    </div>

    <div class="card">
      <div class="card-head"><span>测试目标</span><span class="muted">连通性测试所请求的地址</span></div>
      <div class="card-body">
        <div class="settings-bar">
          <input class="input" v-model="testUrl" placeholder="留空默认面板网关自身" @keyup.enter="saveTestUrl" />
          <button class="btn" type="button" :disabled="savingUrl" @click="saveTestUrl">{{ savingUrl ? '保存中...' : '保存' }}</button>
        </div>
        <div class="hint">留空时测试请求面板网关自身的 /v1/models;填写后按其地址经代理访问。</div>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><span>平台代理</span><span class="muted">{{ items.length }} 个平台</span></div>
      <div v-if="items.length" class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th>平台</th><th>代理地址</th><th>协议</th><th>启用</th><th>连通性</th><th class="r">操作</th></tr></thead>
          <tbody>
            <tr v-for="p in items" :key="p.id">
              <td><div class="plat-cell"><span class="plat-name">{{ p.name }}</span><span class="plat-key mono">{{ p.key }}</span></div></td>
              <td><span v-if="p.proxy" class="mono proxy-addr">{{ p.proxy }}</span><span v-else class="muted">(空 = 直连)</span></td>
              <td><span class="badge dim">{{ protoOf(p.proxy) }}</span></td>
              <td>
                <button class="switch" :class="{ on: isProxyEnabled(p) }" type="button" :disabled="busy === p.id" :aria-label="`切换 ${p.name} 代理启用`" @click="toggleEnabled(p)"><span></span></button>
              </td>
              <td><TestCase :result="results[p.id]" /></td>
              <td class="r"><div class="row-actions"><button class="btn ghost sm" type="button" :disabled="testing === p.id" @click="testOne(p)">{{ testing === p.id ? '测试中...' : '测试' }}</button><button class="btn ghost sm" type="button" :disabled="busy === p.id" @click="openEdit(p)">编辑代理</button></div></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state"><strong>暂无平台</strong><span>请先在「平台接入」添加平台后配置出口代理。</span></div>
    </div>

    <div v-if="dialog.show" class="mask open" @click.self="closeEdit"></div>
    <div v-if="dialog.show" class="modal open" role="dialog" aria-modal="true">
      <div class="modal-head"><span>编辑代理 · {{ dialog.name }}</span><span class="spacer"></span><button class="btn ghost icon" type="button" @click="closeEdit">×</button></div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field"><label>代理地址(HTTP 或 SOCKS5)</label><input class="input" v-model="dialog.proxy" placeholder="socks5h://127.0.0.1:1080 或 http://127.0.0.1:7890" /><span class="hint">支持 socks5h:// / socks5:// / http:// / https://。留空表示直连。</span></div>
          <div class="field">
            <label>启用代理</label>
            <div class="switch-line"><button class="switch" :class="{ on: dialog.enabled }" type="button" @click="dialog.enabled = !dialog.enabled"><span></span></button><span class="switch-text">{{ dialog.enabled ? '启用' : '停用' }}</span></div>
            <span class="hint">关 = 保留地址但不使用,该平台账号回退直连。</span>
          </div>
        </div>
        <div v-if="dialog.error" class="modal-error">{{ dialog.error }}</div>
      </div>
      <div class="modal-foot">
        <button class="btn danger" type="button" :disabled="saving || !dialog.orig" @click="clearProxy">清除地址</button>
        <span class="spacer"></span>
        <button class="btn" type="button" :disabled="saving" @click="closeEdit">取消</button>
        <button class="btn primary" type="button" :disabled="saving" @click="saveProxy">{{ saving ? '保存中...' : '保存' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getPlatforms, getSettings, saveSettings, updatePlatform, testPlatformProxies } from '../api'
import { toastOk, toastErr } from '../lib/toast'

// 连通性结果单元格(内联小组件,避免额外文件)
const TestCase = {
  props: { result: { type: Object, default: null } },
  template: `
    <span v-if="!result" class="muted">未测试</span>
    <span v-else-if="result.running" class="muted">测试中...</span>
    <span v-else class="badge" :class="result.ok ? 'ok' : 'err'"><span class="dot"></span>{{ result.ok ? '✅ ' : '❌ ' }}{{ result.msg }}<template v-if="result.ms != null"> · {{ result.ms }}ms</template></span>`,
}

const items = ref([])
const loading = ref(false)
const busy = ref(null)
const testingAll = ref(false)
const testing = ref(null)
const saving = ref(false)
const testUrl = ref('')
const savingUrl = ref(false)
const results = ref({})
const dialog = ref({ show: false, id: null, name: '', proxy: '', enabled: true, orig: '', error: '' })

const errMsg = (e, fallback) => (e.response?.data?.detail || e.message || fallback)

function protoOf(proxy) {
  const v = String(proxy || '').trim().toLowerCase()
  if (!v) return '—'
  if (v.startsWith('socks5h://') || v.startsWith('socks5://')) return 'SOCKS5'
  if (v.startsWith('http://') || v.startsWith('https://')) return 'HTTP'
  return '—'
}
// 后端 adapter_for 语义:proxy_enabled 缺省视为启用
const isProxyEnabled = (p) => p.proxy_enabled === undefined || p.proxy_enabled === null ? true : !!p.proxy_enabled

async function load() {
  loading.value = true
  try {
    const r = await getPlatforms()
    items.value = r.items || []
  } catch (e) {
    toastErr('加载平台失败:' + errMsg(e, '未知错误'))
  } finally {
    loading.value = false
  }
}

async function loadSettings() {
  try {
    const s = await getSettings()
    testUrl.value = s.proxy_test_url || ''
  } catch (e) {
    toastErr('加载设置失败:' + errMsg(e, '未知错误'))
  }
}

async function saveTestUrl() {
  savingUrl.value = true
  try {
    await saveSettings({ proxy_test_url: testUrl.value.trim() })
    toastOk('测试目标已保存')
  } catch (e) {
    toastErr('保存失败:' + errMsg(e, '未知错误'))
  } finally {
    savingUrl.value = false
  }
}

function applyResults(list) {
  const next = { ...results.value }
  for (const r of list || []) next[r.platform_id] = { ok: !!r.ok, msg: r.msg || (r.ok ? 'HTTP OK' : '失败'), ms: r.ms != null ? r.ms : null }
  results.value = next
}

async function testAll() {
  testingAll.value = true
  try {
    const r = await testPlatformProxies([])
    applyResults(r.items)
    const list = r.items || []
    const ok = list.filter((x) => x.ok).length
    if (!list.length) toastErr('没有可测试的代理(需已配置代理且启用)')
    else if (ok === list.length) toastOk(`连通性测试通过:${ok}/${list.length}`)
    else toastErr(`测试完成:${ok}/${list.length} 通过`)
  } catch (e) {
    toastErr('测试失败:' + errMsg(e, '未知错误'))
  } finally {
    testingAll.value = false
  }
}

async function testOne(p) {
  testing.value = p.id
  results.value = { ...results.value, [p.id]: { running: true } }
  try {
    const r = await testPlatformProxies([p.id])
    const item = (r.items || [])[0]
    if (item) applyResults([item])
    else results.value = { ...results.value, [p.id]: null }
    if (item && item.ok) toastOk(`「${p.name}」代理可用${item.ms != null ? ` · ${item.ms}ms` : ''}`)
    else if (item) toastErr(`「${p.name}」代理不可用:${item.msg}`)
  } catch (e) {
    results.value = { ...results.value, [p.id]: { ok: false, msg: '请求失败', ms: null } }
    toastErr('测试失败:' + errMsg(e, '未知错误'))
  } finally {
    testing.value = null
  }
}

async function toggleEnabled(p) {
  const next = !isProxyEnabled(p)
  busy.value = p.id
  try {
    await updatePlatform(p.id, { proxy_enabled: next })
    toastOk(`「${p.name}」代理已${next ? '启用' : '停用'}${!next && p.proxy ? '(回退直连)' : ''}`)
    await load()
  } catch (e) {
    toastErr('操作失败:' + errMsg(e, '未知错误'))
  } finally {
    busy.value = null
  }
}

function openEdit(p) {
  dialog.value = { show: true, id: p.id, name: p.name, proxy: p.proxy || '', enabled: isProxyEnabled(p), orig: p.proxy || '', error: '' }
}

function closeEdit() {
  dialog.value.show = false
}

async function saveProxy() {
  const d = dialog.value
  const proxy = d.proxy.trim()
  saving.value = true
  d.error = ''
  try {
    await updatePlatform(d.id, { proxy, proxy_enabled: d.enabled })
    toastOk('代理已保存')
    dialog.value.show = false
    await load()
  } catch (e) {
    d.error = errMsg(e, '未知错误')
    toastErr('保存失败:' + d.error)
  } finally {
    saving.value = false
  }
}

async function clearProxy() {
  const d = dialog.value
  try {
    await ElMessageBox.confirm(`确认清除「${d.name}」的代理地址?清除后该平台将直连。`, '清除确认', { confirmButtonText: '清除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  saving.value = true
  d.error = ''
  try {
    await updatePlatform(d.id, { proxy: '' })
    toastOk('代理地址已清除')
    dialog.value.show = false
    await load()
  } catch (e) {
    d.error = errMsg(e, '未知错误')
    toastErr('清除失败:' + d.error)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadSettings()])
})
</script>

<style scoped>
.settings-bar { display: flex; gap: 8px; align-items: center; }
.settings-bar .input { flex: 1; min-width: 0; }
.plat-cell { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.plat-name { font-weight: 600; }
.plat-key { color: var(--text-3); font-size: 11px; }
.proxy-addr { color: var(--text-2); overflow-wrap: anywhere; }
.row-actions { display: flex; gap: 4px; justify-content: flex-end; flex-wrap: wrap; }
.switch-line { display: flex; align-items: center; gap: 8px; margin-top: 2px; }
.switch-text { font-size: 12px; color: var(--text-2); }
.spacer { flex: 1; }
.hint { font-size: 11px; color: var(--text-3); margin-top: 6px; }
.modal-error { margin-top: 12px; padding: 8px 10px; border-radius: var(--radius-sm); background: var(--danger-soft); color: var(--danger); font-size: 12px; overflow-wrap: anywhere; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 34px 16px; color: var(--text-3); text-align: center; }
.empty-state strong { color: var(--text-2); font-size: 13px; }
.modal { width: min(560px, calc(100vw - 32px)); }
.modal-head .btn.icon { font-size: 20px; line-height: 1; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.form-grid .field { min-width: 0; }
@media (max-width: 560px) { .form-grid { grid-template-columns: 1fr; } }
</style>
