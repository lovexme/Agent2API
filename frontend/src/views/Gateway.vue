<template>
  <div class="view-wrap">
    <div class="page-head">
      <div><div class="page-title">模型路由</div><div class="page-desc">OpenAI 兼容网关 /v1 · 模型名 → 平台通道</div></div>
      <div class="head-actions"><button class="pill mono gateway-url" type="button" @click="copy(baseUrl)">{{ baseUrl }} <span class="url-copy">复制</span></button><button class="btn primary" :disabled="loadingModels" @click="loadModels">{{ loadingModels ? '加载中…' : '重新加载' }}</button></div>
    </div>
    <div class="card">
      <div class="card-head"><span>可用模型与路由</span><span class="muted">{{ models.length }} 个模型</span></div>
      <div v-if="models.length" class="tbl-wrap"><table class="tbl"><thead><tr><th>模型 ID</th><th>平台</th><th>路由状态</th><th class="r">操作</th></tr></thead><tbody><tr v-for="m in models" :key="m.id"><td class="mono">{{ m.id }}</td><td>{{ m.owned_by || '自动路由' }}</td><td><span class="badge ok"><span class="dot"></span>可用</span></td><td class="r"><button class="btn ghost sm" type="button" @click="copy(m.id)">复制 ID</button></td></tr></tbody></table></div>
      <div v-else class="empty-state"><strong>暂无可调用模型</strong><span>请先在「账号管理」接入有效账号，模型 ID 将按平台前缀自动生成。</span></div>
    </div>
    <div class="card gateway-note"><div class="card-head">接入说明</div><div class="card-body"><p>所有请求通过统一的 OpenAI 兼容地址进入网关，模型名称会被路由到对应平台，并在有效账号之间轮询。</p><div class="mono endpoint-line">{{ baseUrl }}/chat/completions</div><div class="note-grid"><div><span class="muted">Gateway Key</span><button class="mono inline-copy" type="button" @click="copy(key)">{{ key }} · 复制</button></div><div><span class="muted">Origin</span><span class="mono">{{ origin }}</span></div></div></div></div>
    <div class="card"><div class="card-head"><span>请求日志</span><span class="muted">最近 20 条</span></div><div v-if="logs.length" class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>平台</th><th>模型</th><th>结果</th><th class="r">耗时</th></tr></thead><tbody><tr v-for="l in logs" :key="l.id"><td class="muted mono">{{ l.created_at }}</td><td>{{ l.platform_key }}</td><td class="mono">{{ l.model }}</td><td><span :class="l.ok ? 'badge ok' : 'badge err'">{{ l.ok ? '成功' : '失败 · ' + (l.err?.slice(0, 42) || '') }}</span></td><td class="r num muted">{{ l.latency_ms }} ms</td></tr></tbody></table></div><div v-else class="empty-state compact">暂无请求日志</div></div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSettings, getLogs } from '../api'
import { toastOk, toastErr } from '../lib/toast'
import { copyText } from '../lib/clipboard'

const key = ref('')
const models = ref([])
const logs = ref([])
const loadingModels = ref(false)

const origin = computed(() => window.location.origin)
const baseUrl = computed(() => origin.value + '/v1')
const codeText = computed(() => `curl ${baseUrl.value}/chat/completions \\\n  -H "Authorization: Bearer ${key.value}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "tabbit-domestic/GLM-5.1",\n       "messages": [{"role": "user", "content": "你好"}]}'`)

async function copy(text) {
  const ok = await copyText(text)
  if (ok) toastOk('已复制到剪贴板')
  else toastErr('复制失败,请手动选择')
}

async function loadModels() {
  loadingModels.value = true
  try {
    const r = await fetch(baseUrl.value + '/models', { headers: { Authorization: 'Bearer ' + key.value } })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    models.value = d.data || []
  } catch (e) {
    toastErr('读取模型失败：' + e.message)
  } finally {
    loadingModels.value = false
  }
}

async function load() {
  // 设置与日志各自独立成败:日志接口失败不再连累 gateway_key 加载
  const [s, lg] = await Promise.allSettled([getSettings(), getLogs({ limit: 20 })])
  if (s.status === 'fulfilled') {
    if (s.value.gateway_key) key.value = s.value.gateway_key
  } else {
    toastErr('加载网关设置失败:' + (s.reason?.response?.data?.detail || s.reason?.message || s.reason))
  }
  if (lg.status === 'fulfilled') {
    logs.value = lg.value.items || []
  } else {
    toastErr('加载请求日志失败:' + (lg.reason?.response?.data?.detail || lg.reason?.message || lg.reason))
  }
}


onMounted(async () => {
  await load()
  await loadModels()
})
</script>

<style scoped>
.gateway-url{cursor:pointer;max-width:min(420px,100%);overflow:hidden;text-overflow:ellipsis}.url-copy{color:var(--primary);font-family:var(--font-sans);font-size:11px;margin-left:4px}.gateway-note{margin-top:12px}.gateway-note p{color:var(--text-2);margin-bottom:12px}.endpoint-line{display:block;padding:10px 12px;background:var(--surface-inset);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--primary);overflow-x:auto}.note-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.note-grid>div{display:flex;align-items:center;gap:8px;min-width:0}.note-grid .muted{flex:0 0 auto;font-size:11px}.inline-copy{border:0;background:transparent;color:var(--text);padding:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.empty-state{display:flex;flex-direction:column;align-items:center;gap:4px;padding:32px 16px;color:var(--text-3);text-align:center}.empty-state strong{color:var(--text-2);font-size:13px}.empty-state.compact{padding:28px 16px}@media(max-width:640px){.note-grid{grid-template-columns:minmax(0,1fr)}.gateway-url{width:100%;justify-content:flex-start}}</style>
