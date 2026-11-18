<template>
  <div class="services-view">
    <div class="page-head">
      <div><div class="page-title">工具服务</div><div class="page-desc">客户端工具服务 · 上游提供商与能力配置</div></div>
      <div class="head-actions"><button class="btn primary" @click="openCreate">+ 新增服务</button></div>
    </div>

    <div class="card">
      <div class="card-head"><span>服务列表</span><span class="muted">{{ items.length }} 个服务</span></div>
      <div v-if="items.length" class="tbl-wrap"><table class="tbl">
        <thead><tr><th>名称</th><th>地址</th><th class="c">工具数</th><th>协议</th><th>状态</th><th>更新时间</th><th class="r">操作</th></tr></thead>
        <tbody>
          <tr v-for="s in items" :key="s.id">
            <td><b>{{ s.name }}</b></td>
            <td class="mono addr">{{ s.url || '—' }}</td>
            <td class="c num">{{ toolCount(s) }}</td>
            <td><div class="proto">
              <span class="badge" :class="s.skill_enabled ? 'blue' : 'dim'">Skill</span>
              <span class="badge" :class="s.mcp_enabled ? 'blue' : 'dim'">MCP</span>
              <span class="badge" :class="s.rest_enabled ? 'blue' : 'dim'">REST</span>
            </div></td>
            <td><span class="badge" :class="s.enabled ? 'ok' : 'dim'"><span class="dot"></span>{{ s.enabled ? '已启用' : '已停用' }}</span></td>
            <td class="muted mono">{{ s.updated_at || '—' }}</td>
            <td class="r"><div class="row-actions">
              <button class="btn ghost sm" :disabled="busy === s.id" @click="doTest(s)">{{ busy === s.id ? '测试中...' : '测试' }}</button>
              <button class="btn sm" @click="openEdit(s)">编辑</button>
              <button class="btn sm danger" @click="doDelete(s)">删除</button>
            </div></td>
          </tr>
        </tbody>
      </table></div>
      <div v-else class="empty-state"><strong>暂无工具服务</strong><span>点击右上角「+ 新增服务」登记一个客户端工具服务。</span></div>
    </div>

    <div class="card">
      <div class="card-head"><span>能力配置</span><span class="muted">网络搜索 / 视觉分析</span></div>
      <div class="card-body">
        <div class="cap-block">
          <div class="cap-title">网络搜索</div>
          <div class="form-grid">
            <div class="field span2">
              <label>搜索提供商(多选)</label>
              <div class="chips">
                <button v-for="p in WEBSEARCH_PROVIDERS" :key="p" type="button" class="chip"
                        :class="{ on: cap.websearchProviders.includes(p) }" @click="toggleProvider(p)">{{ p }}</button>
              </div>
              <span class="hint">已选:{{ cap.websearchProviders.length ? cap.websearchProviders.join(', ') : '(未选择)' }}</span>
            </div>
            <div class="field span2">
              <label>搜索 Key(JSON 字符串)</label>
              <textarea class="input area" v-model="cap.websearchKeys" spellcheck="false" placeholder='{"tavily": "tvly-xxxx", "firecrawl": "fc-xxxx"}'></textarea>
              <span class="hint">形如 {"提供商": "Key"} 的 JSON,留空表示无需 Key。</span>
            </div>
            <div class="field"><label>最大查询数</label><input class="input" v-model="cap.maxQueries" inputmode="numeric" placeholder="10" /></div>
            <div class="field"><label>结果去重</label><div class="switch-line"><div class="switch" :class="{ on: cap.dedupe }" @click="cap.dedupe = !cap.dedupe"></div><span class="muted">{{ cap.dedupe ? '开启' : '关闭' }}</span></div></div>
          </div>
        </div>

        <div class="cap-block">
          <div class="cap-title">视觉分析</div>
          <div class="form-grid">
            <div class="field"><label>提供商</label><input class="input" v-model="cap.visionProvider" placeholder="如 openai / qwen / 自定义" /></div>
            <div class="field"><label>模型</label><input class="input" v-model="cap.visionModel" placeholder="如 gpt-4o-mini" /></div>
            <div class="field"><label>API Key</label>
              <div class="key-line"><input class="input" :type="showVisionKey ? 'text' : 'password'" v-model="cap.visionKey" autocomplete="off" placeholder="留空表示不需要" /><button class="btn sm" type="button" @click="showVisionKey = !showVisionKey">{{ showVisionKey ? '隐藏' : '显示' }}</button></div>
            </div>
            <div class="field"><label>调用模式</label><select class="select" v-model="cap.visionMode"><option value="http">http(直连 HTTP 接口)</option><option value="local">local(本地桥接脚本)</option></select></div>
            <div class="field span2"><label>端点 URL</label><input class="input" v-model="cap.visionEndpoint" placeholder="https://api.example.com/v1/chat/completions" /></div>
          </div>
        </div>

        <div class="cap-actions"><button class="btn primary" :disabled="savingCap" @click="saveCap">{{ savingCap ? '保存中...' : '保存能力配置' }}</button><button class="btn" :disabled="loadingCap" @click="loadCap">重新读取</button></div>
      </div>
    </div>

    <div v-if="showForm" class="mask open" @click.self="showForm = false"><div class="modal open service-modal">
      <div class="modal-head"><span>{{ editing ? '编辑服务' : '新增服务' }}</span><button class="btn ghost icon" @click="showForm = false">×</button></div>
      <div class="modal-body"><div class="form-grid">
        <div class="field"><label>名称</label><input class="input" v-model="form.name" placeholder="如 本地搜索网关" /></div>
        <div class="field"><label>执行超时(秒)</label><input class="input" v-model="form.timeout_s" inputmode="numeric" placeholder="60" /></div>
        <div class="field span2"><label>服务地址 URL</label><input class="input" v-model="form.url" placeholder="https://tools.example.com/mcp" /></div>
        <div class="field span2"><label>内部调用 API Key</label>
          <div class="key-line"><input class="input" :type="showKey ? 'text' : 'password'" v-model="form.internal_key" autocomplete="off" placeholder="服务间鉴权用,可留空" /><button class="btn sm" type="button" @click="showKey = !showKey">{{ showKey ? '隐藏' : '显示' }}</button></div>
        </div>
        <div class="field span2"><label>协议</label>
          <div class="switches">
            <div class="switch-line"><div class="switch" :class="{ on: form.skill_enabled }" @click="form.skill_enabled = !form.skill_enabled"></div><span>Skill</span></div>
            <div class="switch-line"><div class="switch" :class="{ on: form.mcp_enabled }" @click="form.mcp_enabled = !form.mcp_enabled"></div><span>MCP</span></div>
            <div class="switch-line"><div class="switch" :class="{ on: form.rest_enabled }" @click="form.rest_enabled = !form.rest_enabled"></div><span>REST</span></div>
            <div class="switch-line"><div class="switch" :class="{ on: form.enabled }" @click="form.enabled = !form.enabled"></div><span>启用</span></div>
          </div>
        </div>
        <div class="field span2"><label>工具列表(JSON 数组)</label><textarea class="input area" v-model="form.toolsText" spellcheck="false" placeholder='[{"name": "search", "desc": "关键词搜索"}]'></textarea><span class="hint">留空或 [] 表示无工具;保存时会校验 JSON 合法性。</span></div>
      </div></div>
      <div class="modal-foot"><button class="btn" @click="showForm = false">取消</button><button class="btn primary" :disabled="saving" @click="save">{{ saving ? '保存中...' : '保存' }}</button></div>
    </div></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getServices, createService, updateService, deleteService, testService, getSettings, saveSettings } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const WEBSEARCH_PROVIDERS = ['tavily', 'querit', 'firecrawl', 'ollama']

const items = ref([])
const busy = ref(null)
const showForm = ref(false)
const editing = ref(null)
const saving = ref(false)
const showKey = ref(false)
const showVisionKey = ref(false)
const savingCap = ref(false)
const loadingCap = ref(false)

const form = ref(blankForm())
const cap = ref(blankCap())

function blankForm() {
  return { name: '', url: '', timeout_s: '60', internal_key: '', skill_enabled: false, mcp_enabled: false, rest_enabled: false, enabled: true, toolsText: '[]' }
}

function blankCap() {
  return { websearchProviders: [], websearchKeys: '{}', maxQueries: '10', dedupe: true, visionProvider: '', visionModel: '', visionKey: '', visionMode: 'http', visionEndpoint: '' }
}

const errMsg = (e) => e?.response?.data?.detail || e?.message || String(e)
const toolCount = (s) => (Array.isArray(s.tools_json) ? s.tools_json.length : 0)

async function load() {
  try {
    const r = await getServices()
    items.value = r.items || []
  } catch (e) {
    toastErr('加载服务失败:' + errMsg(e))
  }
}

function openCreate() {
  editing.value = null
  form.value = blankForm()
  showKey.value = false
  showForm.value = true
}

function openEdit(s) {
  editing.value = s
  form.value = {
    name: s.name || '',
    url: s.url || '',
    timeout_s: String(s.timeout_s ?? 60),
    internal_key: s.internal_key || '',
    skill_enabled: !!s.skill_enabled,
    mcp_enabled: !!s.mcp_enabled,
    rest_enabled: !!s.rest_enabled,
    enabled: !!s.enabled,
    toolsText: JSON.stringify(Array.isArray(s.tools_json) ? s.tools_json : [], null, 2),
  }
  showKey.value = false
  showForm.value = true
}

async function save() {
  const f = form.value
  if (!f.name.trim()) return toastErr('请填写服务名称')

  let tools = []
  const raw = (f.toolsText || '').trim()
  if (raw) {
    try {
      tools = JSON.parse(raw)
    } catch (e) {
      return toastErr('工具列表不是合法 JSON:' + e.message)
    }
    if (!Array.isArray(tools)) return toastErr('工具列表必须是 JSON 数组')
  }
  const timeout = parseInt(f.timeout_s, 10)
  if (Number.isNaN(timeout) || timeout < 1) return toastErr('执行超时需为正整数秒')

  saving.value = true
  try {
    if (editing.value) {
      await updateService(editing.value.id, {
        name: f.name.trim(), url: f.url.trim(), tools_json: tools,
        enabled: f.enabled ? 1 : 0, timeout_s: timeout, internal_key: f.internal_key.trim(),
        skill_enabled: f.skill_enabled ? 1 : 0, mcp_enabled: f.mcp_enabled ? 1 : 0, rest_enabled: f.rest_enabled ? 1 : 0,
      })
      toastOk('服务已更新')
    } else {
      await createService({
        name: f.name.trim(), url: f.url.trim(), tools_json: tools,
        enabled: f.enabled, timeout_s: timeout, internal_key: f.internal_key.trim(),
        skill_enabled: f.skill_enabled, mcp_enabled: f.mcp_enabled, rest_enabled: f.rest_enabled, config_json: {},
      })
      toastOk('服务已添加')
    }
    showForm.value = false
    await load()
  } catch (e) {
    toastErr('保存失败:' + errMsg(e))
  } finally {
    saving.value = false
  }
}

async function doTest(s) {
  busy.value = s.id
  try {
    const r = await testService(s.id)
    if (r.reachable) toastOk(`连通:${r.ms}ms`)
    else toastErr(`失败:${r.status || '不可达'}`)
  } catch (e) {
    toastErr('测试失败:' + errMsg(e))
  } finally {
    busy.value = null
  }
}

async function doDelete(s) {
  try {
    await ElMessageBox.confirm(`确认删除服务「${s.name}」?`, '删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deleteService(s.id)
    toastOk('服务已删除')
    await load()
  } catch (e) {
    toastErr('删除失败:' + errMsg(e))
  }
}

function toggleProvider(p) {
  const list = cap.value.websearchProviders
  const i = list.indexOf(p)
  if (i >= 0) list.splice(i, 1)
  else list.push(p)
}

async function loadCap() {
  loadingCap.value = true
  try {
    const s = await getSettings()
    cap.value = {
      websearchProviders: String(s.tool_websearch_providers || '').split(',').map((x) => x.trim()).filter(Boolean),
      websearchKeys: s.tool_websearch_keys || '{}',
      maxQueries: String(s.tool_websearch_max_queries ?? '10'),
      dedupe: String(s.tool_websearch_dedupe ?? '1') !== '0',
      visionProvider: s.tool_vision_provider || '',
      visionModel: s.tool_vision_model || '',
      visionKey: s.tool_vision_key || '',
      visionMode: s.tool_vision_mode || 'http',
      visionEndpoint: s.tool_vision_endpoint || '',
    }
  } catch (e) {
    toastErr('读取能力配置失败:' + errMsg(e))
  } finally {
    loadingCap.value = false
  }
}

async function saveCap() {
  const c = cap.value
  if (c.websearchKeys.trim()) {
    try { JSON.parse(c.websearchKeys) } catch (e) { return toastErr('搜索 Key 不是合法 JSON:' + e.message) }
  }
  savingCap.value = true
  try {
    await saveSettings({
      tool_websearch_providers: c.websearchProviders.join(','),
      tool_websearch_keys: c.websearchKeys,
      tool_websearch_max_queries: String(c.maxQueries),
      tool_websearch_dedupe: c.dedupe ? '1' : '0',
      tool_vision_provider: c.visionProvider,
      tool_vision_model: c.visionModel,
      tool_vision_key: c.visionKey,
      tool_vision_mode: c.visionMode,
      tool_vision_endpoint: c.visionEndpoint,
    })
    toastOk('能力配置已保存')
  } catch (e) {
    toastErr('保存能力配置失败:' + errMsg(e))
  } finally {
    savingCap.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadCap()])
})
</script>

<style scoped>
.services-view .addr { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.proto { display: flex; gap: 4px; }
.badge .dot { width: 6px; height: 6px; box-shadow: none; }
.row-actions { display: inline-flex; gap: 6px; justify-content: flex-end; }
.tbl td .row-actions .btn { white-space: nowrap; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 34px 16px; color: var(--text-3); text-align: center; }
.empty-state strong { color: var(--text-2); font-size: 13px; }
.card + .card { margin-top: 12px; }

.cap-block + .cap-block { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.cap-title { font-size: 12.5px; font-weight: 650; color: var(--text-2); margin-bottom: 12px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 14px; }
.form-grid .field { min-width: 0; }
.form-grid .span2 { grid-column: 1 / -1; }
.input.area { height: auto; min-height: 74px; padding: 8px 10px; font-family: var(--font-mono); font-size: 11.5px; line-height: 1.5; resize: vertical; white-space: pre; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { height: 26px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--border-strong); background: var(--surface-2); color: var(--text-2); font-size: 12px; cursor: pointer; }
.chip.on { background: var(--primary-soft); border-color: var(--primary); color: var(--primary); }
.switch-line { display: flex; align-items: center; gap: 8px; height: 32px; }
.switches { display: flex; flex-wrap: wrap; gap: 0 20px; }
.switches .switch-line span { font-size: 12px; color: var(--text-2); }
.key-line { display: flex; gap: 6px; }
.key-line .input { flex: 1 1 auto; min-width: 0; }
.cap-actions { display: flex; gap: 8px; margin-top: 16px; }
.service-modal { width: min(600px, calc(100vw - 32px)); }
.service-modal .btn.icon { margin-left: auto; font-size: 20px; line-height: 1; }
@media (max-width: 560px) { .form-grid { grid-template-columns: 1fr; } .services-view .addr { max-width: 160px; } }
</style>
