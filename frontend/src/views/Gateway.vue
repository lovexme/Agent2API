<template>
  <div>
    <div class="heading">
      <div>
        <div class="eyebrow">OpenAI 兼容接口</div>
        <h1>统一网关</h1>
        <div class="sub">一个入口，路由所有已接入账号池</div>
      </div>
      <span class="state" :class="models.length ? 'active-state' : 'unknown-state'">{{ models.length ? '运行中' : '等待接入' }}</span>
    </div>

    <div class="gateway-panel">
      <h2>接入信息</h2>
      <div class="field" style="margin-bottom: 12px">
        <label>Base URL</label>
        <div class="keyrow">
          <input :value="baseUrl" readonly @click="copy(baseUrl)" />
          <button class="btn secondary sm" @click="copy(baseUrl)">复制</button>
        </div>
        <span class="hint">当前访问入口为 {{ origin }}；本机亦可通过 IPv6 访问（直接使用面板地址 + /v1 即可）。</span>
      </div>
      <div class="field">
        <label>网关密钥（Gateway Key）</label>
        <div class="keyrow">
          <input :value="key" readonly @click="copy(key)" />
          <button class="btn secondary sm" @click="copy(key)">复制</button>
        </div>
        <span class="hint">调用 /v1 接口时作为 Bearer 请求头；可在「设置」中修改。</span>
      </div>
      <div class="notice">请求会按模型前缀路由到对应平台，并在该平台的有效账号之间轮询。形如 <code>tabbit-domestic/GLM-5.1</code> 的模型 ID 可精确路由。</div>
    </div>

    <div class="gateway-panel">
      <h2>快速开始</h2>
      <pre class="code">curl {{ baseUrl }}/chat/completions \
  -H "Authorization: Bearer {{ key }}" \
  -H "Content-Type: application/json" \
  -d '{"model": "tabbit-domestic/GLM-5.1",
       "messages": [{"role": "user", "content": "你好"}]}'</pre>
      <button class="btn secondary sm" style="margin-top: 12px" @click="copy(codeText)">复制示例</button>
    </div>

    <div class="gateway-panel">
      <div class="section-head" style="margin-top: 0"><h2>可用模型</h2><button class="btn secondary sm" :disabled="loadingModels" @click="loadModels">{{ loadingModels ? '加载中…' : '重新加载' }}</button></div>
      <div v-if="models.length" class="model-list">
        <span v-for="m in models" :key="m.id" class="model">{{ m.id }}<small>{{ m.owned_by }}</small></span>
      </div>
      <div v-else class="empty" style="padding: 26px 16px">
        <h3>暂无可调用模型</h3>
        <p>请先在「账号管理」接入有效账号（平台前缀 + 模型名组成模型 ID）</p>
      </div>
    </div>

    <div class="gateway-panel">
      <div class="section-head" style="margin-top: 0"><h2>请求日志</h2><span class="muted">最近 20 条</span></div>
      <div class="table-wrap" v-if="logs.length">
        <table class="table">
          <thead><tr><th>时间</th><th>平台</th><th>模型</th><th>结果</th><th>耗时</th></tr></thead>
          <tbody>
            <tr v-for="l in logs" :key="l.id">
              <td class="muted">{{ l.created_at }}</td>
              <td>{{ l.platform_key }}</td>
              <td>{{ l.model }}</td>
              <td><span :class="l.ok ? 'ok' : 'fail'">{{ l.ok ? '✓ 成功' : '✗ ' + l.err.slice(0, 42) }}</span></td>
              <td class="muted">{{ l.latency_ms }} ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty" style="padding: 26px 16px"><h3>暂无请求日志</h3></div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSettings, getLogs } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const key = ref('aam-local-key')
const models = ref([])
const logs = ref([])
const loadingModels = ref(false)

const origin = computed(() => window.location.origin)
const baseUrl = computed(() => origin.value + '/v1')
const codeText = computed(() => `curl ${baseUrl.value}/chat/completions \\\n  -H "Authorization: Bearer ${key.value}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "tabbit-domestic/GLM-5.1",\n       "messages": [{"role": "user", "content": "你好"}]}'`)

function copy(text) {
  navigator.clipboard?.writeText(text).then(() => toastOk('已复制到剪贴板')).catch(() => toastErr('复制失败，请手动选择'))
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
  try {
    const [s, lg] = await Promise.all([getSettings(), getLogs({ limit: 20 })])
    if (s.gateway_key) key.value = s.gateway_key
    logs.value = lg.items || []
  } catch (e) {
    toastErr('加载网关信息失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => {
  load()
  loadModels()
})
</script>