<template>
  <section class="daily-tasks-view">
    <header class="page-head">
      <div>
        <div class="page-title">每日任务</div>
        <div class="page-desc">自动签到 / 账号健康检测 · 每日任务运行状态</div>
      </div>
      <div class="head-actions">
        <button class="btn" :disabled="loading || busy" @click="loadDailyTasks">
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
        <button class="btn primary" :disabled="loading || busy || !items.length" @click="runAll">
          {{ busy && !busyId ? '运行中…' : '立即运行' }}
        </button>
      </div>
    </header>

    <div class="kpis">
      <div class="card kpi"><div class="kpi-label">任务总数</div><div class="kpi-value">{{ items.length }}</div><div class="kpi-foot">Trae 账号</div></div>
      <div class="card kpi"><div class="kpi-label">已签到</div><div class="kpi-value">{{ checkedInCount }}</div><div class="kpi-foot"><span class="trend up">今日完成</span></div></div>
      <div class="card kpi"><div class="kpi-label">待签到</div><div class="kpi-value">{{ pendingCount }}</div><div class="kpi-foot">等待执行</div></div>
      <div class="card kpi"><div class="kpi-label">失败</div><div class="kpi-value">{{ failedCount }}</div><div class="kpi-foot">需重试或检查状态</div></div>
    </div>

    <div class="cols-2">
      <div class="card">
        <div class="card-head">自动任务</div>
        <div class="card-body tight">
          <div v-for="task in tasksDef" :key="task.key" class="setting-row task-row" :class="{ expanded: task.key === 'trae' && showAccounts }">
            <div class="setting-info" @click="task.key === 'trae' && (showAccounts = !showAccounts)">
              <div class="setting-title">{{ task.title }}</div>
              <div class="setting-desc">{{ task.schedule }} · {{ task.description }}</div>
            </div>
            <span class="badge" :class="taskBadgeClass(task)">{{ taskStatus(task) }}</span>
            <button v-if="task.key === 'trae'" class="btn sm ghost" :aria-expanded="showAccounts" @click="showAccounts = !showAccounts">{{ showAccounts ? '收起' : '查看' }}</button>
            <button v-else-if="task.key === 'health'" class="switch" :class="{ on: autoCheckEnabled }" :disabled="settingsSaving" aria-label="切换每日自动检测" @click="toggleAutoCheck"><span></span></button>
          </div>
          <div v-if="showAccounts" class="task-accounts">
            <div v-if="!items.length" class="empty compact"><span>暂无 Trae 账号</span></div>
            <div v-for="task in items" :key="task.account_id" class="task-account-row">
              <div class="acct-cell"><span class="avatar">{{ avatarText(task.label || task.account_id) }}</span><div class="acct-copy"><div class="acct-name" :title="task.label || task.account_id">{{ task.label || task.account_id }}</div><div class="acct-meta">#{{ task.account_id }}</div></div></div>
              <span class="badge" :class="statusClass(task)">{{ statusText(task) }}</span>
              <button class="btn sm" :disabled="loading || busy" @click="runTaskCheckin(task)">{{ busyId === task.account_id ? '签到中…' : '签到' }}</button>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">最近执行记录 <span class="muted task-count">{{ history.length }} 条</span></div>
        <div class="card-body tight history-list">
          <div v-for="(entry, index) in history" :key="`${entry.time}-${index}`" class="history-row"><span class="history-time mono">{{ entry.time }}</span><span>{{ entry.text }}</span></div>
          <div v-if="!history.length" class="empty compact"><span>暂无执行记录</span></div>
        </div>
      </div>
    </div>

    <div class="card task-card">
      <div class="card-head">签到状态 <span class="muted task-count">{{ items.length }} 个账号</span></div>
      <div v-loading="loading" class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th>账号</th><th>状态</th><th>说明</th><th class="r">操作</th></tr></thead>
          <tbody>
            <tr v-for="task in items" :key="task.account_id">
              <td><div class="acct-cell"><span class="avatar">{{ avatarText(task.label || task.account_id) }}</span><div class="acct-copy"><div class="acct-name" :title="task.label || task.account_id">{{ task.label || task.account_id }}</div><div class="acct-meta">#{{ task.account_id }}</div></div></div></td>
              <td><span class="badge" :class="statusClass(task)">{{ statusText(task) }}</span></td>
              <td class="task-message" :title="task.message || ''">{{ task.message || '—' }}</td>
              <td class="r"><button class="btn sm" :disabled="loading || busy" @click="runTaskCheckin(task)">{{ busyId === task.account_id ? '签到中…' : '签到' }}</button></td>
            </tr>
            <tr v-if="!items.length && !loading"><td colspan="4"><div class="empty"><strong>{{ loadError ? '每日任务加载失败' : '暂无 Trae 账号' }}</strong><span>{{ loadError || '请先在账号池接入 Trae' }}</span></div></td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card task-card wb-card">
      <div class="card-head">WorkBuddy 每日任务 <span class="muted task-count">{{ wb.loading ? '加载中…' : `${wb.accounts.length} 个账号 · ${wb.gateway || ''}` }}</span>
        <div class="wb-actions">
          <button class="btn sm ghost" :disabled="wb.loading || wb.busy" @click="loadWorkbuddy">刷新</button>
          <button class="btn sm ghost" :disabled="wb.loading || wb.busy" @click="scanWb">扫描任务</button>
          <button class="btn sm" :disabled="wb.loading || wb.busy" @click="checkinWb">一键签到</button>
          <button class="btn sm primary" :disabled="wb.loading || wb.busy" @click="runWb">一键跑任务</button>
        </div>
      </div>
      <div class="wb-schedule">
        <span v-for="(v, k) in wb.schedule" :key="k" class="wb-tag">{{ wbLabel(k) }} {{ v }}</span>
        <span v-if="wb.queue.running" class="badge warn">队列执行中 {{ wb.queue.total }} 项</span>
        <span v-else-if="wb.queue.total" class="badge dim">队列 {{ wb.queue.total }} 项待跑</span>
      </div>
      <div v-if="wb.error" class="wb-error">{{ wb.error }}</div>
      <div class="tbl-wrap" v-loading="wb.loading">
        <table class="tbl">
          <thead><tr><th>账号</th><th>任务进度</th><th>待领奖励</th><th>积分</th><th>最近成功</th><th class="r">状态</th></tr></thead>
          <tbody>
            <tr v-for="a in wb.accounts" :key="a.uid">
              <td><div class="acct-cell"><span class="avatar">{{ (a.nickname || '?').slice(0,1).toUpperCase() }}</span><div class="acct-copy"><div class="acct-name">{{ a.nickname }}</div><div class="acct-meta">{{ a.uid.slice(0,8) }}</div></div></div></td>
              <td><span class="mono">{{ a.tasks_done }} / {{ a.tasks_total }}</span><div class="bar wb-bar"><i :style="{ width: a.tasks_total ? Math.round(a.tasks_done / a.tasks_total * 100) + '%' : '0%' }"></i></div></td>
              <td><span class="badge" :class="a.rewards_pending > 0 ? 'warn' : 'dim'">{{ a.rewards_pending }} 项</span></td>
              <td><span class="mono">{{ a.credits != null ? a.credits : '—' }}{{ a.credits_total ? ' / ' + a.credits_total : '' }}</span></td>
              <td><span class="acct-meta">{{ a.last_success || '—' }}</span></td>
              <td class="r"><span class="badge" :class="a.cooling ? 'err' : 'ok'">{{ a.cooling ? '冷却中' : '正常' }}</span></td>
            </tr>
            <tr v-if="!wb.accounts.length && !wb.loading"><td colspan="6"><div class="empty"><strong>{{ wb.error ? 'WorkBuddy 任务加载失败' : '暂无 WorkBuddy 账号' }}</strong><span>{{ wb.error || '请先在账号池授权 WorkBuddy 账号' }}</span></div></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSettings, saveSettings, getWorkbuddyTasks, scanWorkbuddyTasks, runWorkbuddyTasks, checkinWorkbuddyTasks } from '../api'
import { toastOk, toastErr } from '../lib/toast'
import { ElMessageBox } from 'element-plus'

const items = ref([])
const currentSettings = ref(null)
const loading = ref(false)
const busy = ref(false)
const busyId = ref(null)
const loadError = ref('')
const autoCheckEnabled = ref(false)
const settingsSaving = ref(false)
const showAccounts = ref(false)
const history = ref([])
const wb = ref({ loading: false, busy: false, error: '', gateway: '', accounts: [], queue: { running: false, total: 0, conc: 0 }, schedule: {} })

const tasksDef = [
  { key: 'health', title: '账号健康检测', schedule: '每日 08:00', description: '面板内调度器:检测全部账号状态与积分(双实例自动去重)' },
  { key: 'trae', title: 'Trae 自动签到', schedule: '每日 08:05', description: '对应 crontab 5 8 * * * trae-checkin' },
  { key: 'loomy', title: 'Loomy 会话刷新', schedule: '未配置定时', description: '暂无独立接口' },
  { key: 'expiry', title: '积分到期提醒', schedule: '未配置定时', description: '提醒即将到期的积分' },
]

const checkedInCount = computed(() => items.value.filter((task) => task.checked_in === true || task.checkinOk === true).length)
const failedCount = computed(() => items.value.filter(isFailed).length)
// 待签到只统计明确的「未签到(false)」；checked_in=null 属于状态未知，不计入待签
const pendingCount = computed(() => items.value.filter((task) => !isFailed(task) && (task.checkinOk === false || task.checked_in === false) && !(task.checked_in === true || task.checkinOk === true)).length)

function isFailed(task) {
  if (task.checkinOk === false) return true
  if (task.checkinOk === true) return false
  const st = String(task.status || '').toLowerCase()
  const msg = String(task.message || '')
  return /fail|error|denied|invalid|limi/.test(st) || /失败|异常|错误|拒绝|不可用/.test(msg) || /fail|error/.test(msg)
}
function statusClass(task) { return isFailed(task) ? 'err' : (task.checked_in === true || task.checkinOk === true) ? 'ok' : task.checked_in === false ? 'warn' : 'dim' }
function statusText(task) { return isFailed(task) ? '失败' : (task.checked_in === true || task.checkinOk === true) ? '已签到' : task.checked_in === false ? '待签到' : '未知' }
function avatarText(label) { return String(label || '?').trim().slice(0, 1).toUpperCase() || '?' }
function taskStatus(task) {
  if (task.key === 'health') return autoCheckEnabled.value ? '启用' : '停用'
  if (task.key === 'trae') return !items.value.length ? '暂无 Trae 账号' : checkedInCount.value === items.value.length ? `已签到 ${checkedInCount.value}/${items.value.length}` : `待签到 ${pendingCount.value}/${items.value.length}`
  if (task.key === 'expiry') return '—'
  return '—'
}
function taskBadgeClass(task) {
  if (task.key === 'health') return autoCheckEnabled.value ? 'ok' : 'dim'
  if (task.key === 'trae') return !items.value.length ? 'dim' : checkedInCount.value === items.value.length ? 'ok' : 'warn'
  return task.key === 'expiry' ? 'blue' : 'dim'
}
function appendHistory(text) { history.value.unshift({ time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }), text }) }
async function parseError(response) {
  const raw = await response.text()
  try {
    const body = JSON.parse(raw)
    return body?.detail ? String(body.detail) : (body?.message ? String(body.message) : `HTTP ${response.status}`)
  } catch { return raw ? raw.slice(0, 160) : `HTTP ${response.status}` }
}
async function toggleAutoCheck() {
  if (settingsSaving.value) return
  const next = !autoCheckEnabled.value
  autoCheckEnabled.value = next
  settingsSaving.value = true
  try {
    await saveSettings({ daily_auto_check: next ? 'on' : 'off' })
    toastOk(`账号健康检测已${next ? '启用' : '停用'}`)
  } catch (error) {
    autoCheckEnabled.value = !next
    toastErr('保存失败：' + (error?.message || error))
  } finally {
    settingsSaving.value = false
  }
}

async function loadDailyTasks() {
  loading.value = true
  loadError.value = ''
  try {
    const [tasksRes, settingsRes] = await Promise.allSettled([fetch('/api/daily-tasks'), getSettings()])
    if (tasksRes.status !== 'fulfilled') throw tasksRes.reason
    const response = tasksRes.value
    if (!response.ok) throw new Error(await parseError(response))
    const data = await response.json()
    if (!Array.isArray(data)) throw new Error('接口返回格式不正确')
    items.value = data.map((task) => ({ ...task, checkinOk: null }))
    if (settingsRes.status === 'fulfilled') {
      currentSettings.value = settingsRes.value || null
      autoCheckEnabled.value = settingsRes.value?.daily_auto_check === 'on'
    }
    if (!history.value.length) appendHistory(`已加载 Trae 签到状态（${items.value.length} 个账号）`)
    else appendHistory('签到状态拉取完成')
  } catch (error) {
    items.value = []
    loadError.value = error.message
    toastErr('加载每日任务失败：' + error.message)
  } finally { loading.value = false }
}

async function runTaskCheckin(task = null) {
  busy.value = true
  busyId.value = task?.account_id ?? null
  try {
    const url = task ? `/api/daily-tasks/checkin?account_id=${encodeURIComponent(task.account_id)}` : '/api/daily-tasks/checkin'
    const response = await fetch(url, { method: 'POST' })
    if (!response.ok) throw new Error(await parseError(response))
    const results = await response.json()
    if (!Array.isArray(results)) throw new Error('接口返回格式不正确')
    for (const result of results) {
      const row = items.value.find((item) => item.account_id === result.account_id)
      if (row) { row.checkinOk = result.ok; row.checked_in = result.ok; row.status = result.ok ? 'success' : 'failed'; row.message = result.message || (result.ok ? '签到成功' : '签到失败') }
    }
    const successes = results.filter((result) => result.ok).length
    const failures = results.length - successes
    if (failures) toastErr(`签到完成：${successes} 个成功，${failures} 个失败`)
    else toastOk(task ? (results[0]?.message || '签到成功') : `全部签到完成：${successes} 个账号`)
    if (task) appendHistory(`账号 ${task.label || task.account_id} 签到：${failures ? '失败' : '成功'}`)
    else {
      appendHistory(`Trae 全部签到：${successes} 成功 / ${failures} 失败`)
      try {
        const settings = await getSettings()
        currentSettings.value = settings || null
        autoCheckEnabled.value = settings?.daily_auto_check === 'on'
      } catch { /* 设置刷新失败不影响签到结果 */ }
    }
  } catch (error) { toastErr('签到失败：' + error.message) }
  finally { busy.value = false; busyId.value = null }
}
function runAll() { return runTaskCheckin() }

const WB_LABELS = { checkin: '签到', growth: '成长任务', activity: '活跃上报', travel: '猫猫旅行', keepalive: 'token 保活', blackcat: '黑猫任务' }
const wbLabel = (k) => WB_LABELS[k] || k

async function loadWorkbuddy() {
  wb.value.loading = true
  wb.value.error = ''
  try {
    const d = await getWorkbuddyTasks()
    wb.value.gateway = d.gateway || ''
    wb.value.accounts = Array.isArray(d.accounts) ? d.accounts : []
    wb.value.queue = d.queue || { running: false, total: 0, conc: 0 }
    wb.value.schedule = d.schedule || {}
  } catch (e) {
    wb.value.accounts = []
    wb.value.error = e.response?.data?.detail || e.message || '加载失败'
  } finally { wb.value.loading = false }
}

async function scanWb() {
  wb.value.busy = true
  try {
    const d = await scanWorkbuddyTasks()
    toastOk(`任务扫描完成：${d.accounts ?? 0} 个账号`)
    await loadWorkbuddy()
    appendHistory('WorkBuddy 成长任务已重新扫描')
  } catch (e) { toastErr('扫描失败：' + (e.response?.data?.detail || e.message)) }
  finally { wb.value.busy = false }
}

async function checkinWb() {
  const ok = await ElMessageBox.confirm('将对 WorkBuddy 池内所有账号执行真实签到，继续吗？', '一键签到', { confirmButtonText: '签到', cancelButtonText: '取消', type: 'warning' }).catch(() => false)
  if (!ok) return
  wb.value.busy = true
  try {
    const d = await checkinWorkbuddyTasks()
    toastOk(d.started ? '签到已触发，稍后刷新查看结果' : '签到请求已提交')
    appendHistory('WorkBuddy 一键签到已触发')
    setTimeout(loadWorkbuddy, 6000)
  } catch (e) { toastErr('签到失败：' + (e.response?.data?.detail || e.message)) }
  finally { wb.value.busy = false }
}

async function runWb() {
  const ok = await ElMessageBox.confirm('将对 WorkBuddy 执行一键任务队列（真实调用上游、消耗少量额度），继续吗？', '一键跑任务', { confirmButtonText: '执行', cancelButtonText: '取消', type: 'warning' }).catch(() => false)
  if (!ok) return
  wb.value.busy = true
  try {
    const d = await runWorkbuddyTasks()
    toastOk(`任务队列已启动：${d.total ?? 0} 项`)
    appendHistory(`WorkBuddy 任务队列启动（${d.total ?? 0} 项）`)
    setTimeout(loadWorkbuddy, 6000)
  } catch (e) { toastErr('任务启动失败：' + (e.response?.data?.detail || e.message)) }
  finally { wb.value.busy = false }
}

onMounted(() => { loadDailyTasks(); loadWorkbuddy() })
</script>

<style scoped>
.daily-tasks-view { min-width: 0; color: var(--text); }
.daily-tasks-view .kpis { margin-bottom: 12px; }
.daily-tasks-view .task-card { min-width: 0; margin-top: 12px; }
.daily-tasks-view .task-count { margin-left: auto; font-weight: 400; }
.daily-tasks-view .task-row { cursor: default; }
.daily-tasks-view .task-row .setting-info { cursor: pointer; }
.daily-tasks-view .task-accounts { border-top: 1px solid var(--border); background: var(--surface-2); }
.daily-tasks-view .task-account-row { display: flex; align-items: center; gap: 10px; padding: 9px 16px 9px 28px; border-bottom: 1px solid var(--border); }
.daily-tasks-view .task-account-row:last-child { border-bottom: 0; }
.daily-tasks-view .task-account-row .acct-cell { flex: 1; min-width: 0; }
.daily-tasks-view .acct-copy { min-width: 0; }
.daily-tasks-view .acct-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
.daily-tasks-view .task-message { color: var(--text-2); overflow-wrap: anywhere; }
.daily-tasks-view .history-list { min-height: 190px; }
.daily-tasks-view .history-row { display: flex; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); line-height: 1.4; }
.daily-tasks-view .history-row:last-child { border-bottom: 0; }
.daily-tasks-view .history-time { color: var(--text-3); flex: 0 0 42px; }
.daily-tasks-view .empty { min-height: 170px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: var(--text-3); }
.daily-tasks-view .empty.compact { min-height: 54px; }
.daily-tasks-view .empty strong { color: var(--text); font-size: 13px; }
.daily-tasks-view button:disabled { cursor: not-allowed; opacity: .55; }
.daily-tasks-view .wb-card .card-head { gap: 8px; flex-wrap: wrap; }
.daily-tasks-view .wb-actions { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }
.daily-tasks-view .wb-schedule { display: flex; gap: 6px; flex-wrap: wrap; padding: 8px 16px; border-bottom: 1px solid var(--border); background: var(--surface-2); }
.daily-tasks-view .wb-tag { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); color: var(--text-2); }
.daily-tasks-view .wb-error { padding: 10px 16px; color: var(--err, #e5484d); font-size: 12px; }
.daily-tasks-view .wb-bar { height: 4px; margin-top: 4px; max-width: 90px; }
.daily-tasks-view .wb-bar i { display: block; height: 100%; background: var(--accent, #3b82f6); border-radius: 2px; }
@media (max-width: 767px) {
  .daily-tasks-view .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .daily-tasks-view .kpi { padding: 12px; }
  .daily-tasks-view .page-head { align-items: flex-start; }
  .daily-tasks-view .head-actions { width: 100%; margin-left: 0; }
  .daily-tasks-view .head-actions .btn { flex: 1; }
  .daily-tasks-view .task-row { flex-wrap: wrap; gap: 8px; }
  .daily-tasks-view .task-row .setting-info { flex: 1 1 calc(100% - 90px); }
  .daily-tasks-view .task-account-row { padding-left: 16px; flex-wrap: wrap; }
  .daily-tasks-view table.tbl { min-width: 600px; }
}
</style>
