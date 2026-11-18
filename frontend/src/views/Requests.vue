<template>
  <div class="view-wrap">
    <div class="page-head">
      <div>
        <div class="page-title">请求日志</div>
        <div class="page-desc">网关转发明细 · 状态 / 耗时 / 路由路径</div>
      </div>
      <div class="head-actions">
        <button class="btn" type="button" :disabled="loading" @click="load">
          {{ loading ? '加载中…' : '↻ 刷新' }}
        </button>
      </div>
    </div>

    <div class="card">
      <div class="filters">
        <div class="seg" role="group" aria-label="按状态筛选">
          <button type="button" :class="{ on: statusFilter === 'all' }" @click="statusFilter = 'all'">全部</button>
          <button type="button" :class="{ on: statusFilter === 'ok' }" @click="statusFilter = 'ok'">成功</button>
          <button type="button" :class="{ on: statusFilter === 'err' }" @click="statusFilter = 'err'">失败</button>
        </div>
        <div class="search">
          <input v-model="query" class="input" type="search" placeholder="搜索模型 / 账号…" aria-label="搜索模型或账号" />
        </div>
      </div>

      <div v-if="filteredLogs.length" class="tbl-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>时间</th><th>模型</th><th>账号</th>
              <th>状态</th><th class="r">耗时</th><th>错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in pageLogs" :key="item.id">
              <td class="mono muted time-cell" :title="item.created_at || ''">{{ item.created_at || '—' }}</td>
              <td class="mono model-cell">
                <span class="model-main">{{ modelLabel(item) }}</span>
                <span v-if="modelSub(item)" class="model-sub muted">{{ modelSub(item) }}</span>
              </td>
              <td>
                <div class="acct-cell req-acct">
                  <div class="avatar">{{ acctInitials(item) }}</div>
                  <span class="acct-name" :title="acctName(item)">{{ acctName(item) }}</span>
                </div>
              </td>
              <td><span :class="['badge', item.ok ? 'ok' : 'err']" :title="item.ok ? '网关记录为成功（表内无 HTTP 状态码）' : '网关记录为失败'">{{ item.ok ? '200' : '失败' }}</span></td>
              <td class="r num muted dur">{{ formatDur(item.latency_ms) }}</td>
              <td class="muted error-cell" :title="item.ok ? '' : (item.err || '')">{{ item.ok ? '—' : truncate(item.err) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="filteredLogs.length" class="table-foot">
        <span>共 {{ filteredLogs.length }} 条<template v-if="filteredLogs.length !== logs.length">（全部 {{ logs.length }} 条中筛选）</template></span>
        <div class="pager">
          <button :disabled="page <= 1" @click="page--">‹</button>
          <template v-for="n in pageNumbers" :key="n">
            <button v-if="n === '…'" class="dim" disabled>…</button>
            <button v-else :class="{ on: n === page }" @click="page = n">{{ n }}</button>
          </template>
          <button :disabled="page >= pageCount" @click="page++">›</button>
          <span class="pg-size">每页
            <select class="select" v-model.number="pageSize" style="width:64px;height:26px;font-size:11px;">
              <option :value="50">50</option><option :value="100">100</option><option :value="200">200</option>
            </select>
          </span>
        </div>
      </div>
      <div v-else class="card-body empty-state">
        <strong>{{ loading ? '正在加载请求日志…' : error ? '请求日志暂不可用' : '暂无请求日志' }}</strong>
        <span v-if="!loading && !error && logs.length">没有符合当前筛选条件的记录</span>
        <span v-else-if="error">{{ error }}</span>
      </div>

      <div class="table-foot">
        共 {{ logs.length }} 条 · 成功 {{ successCount }} / 失败 {{ failureCount }}<template v-if="filteredLogs.length !== logs.length"> · 当前筛选 {{ filteredLogs.length }} 条</template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getLogs, getAccounts } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const logs = ref([])
const accountMap = ref(new Map())
const loading = ref(false)
const statusFilter = ref('all')
const query = ref('')
const error = ref('')

const page = ref(1)
const pageSize = ref(50)
const pageCount = computed(() => Math.max(1, Math.ceil(filteredLogs.value.length / pageSize.value)))
const pageLogs = computed(() => filteredLogs.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const pageNumbers = computed(() => {
  const c = pageCount.value, cur = page.value, out = []
  for (let i = 1; i <= c; i++) {
    if (i === 1 || i === c || Math.abs(i - cur) <= 1) out.push(i)
    else if (out[out.length - 1] !== '…') out.push('…')
  }
  return out
})
const filteredLogs = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return logs.value.filter((item) => {
    const statusMatch = statusFilter.value === 'all'
      || (statusFilter.value === 'ok' ? Boolean(item.ok) : !item.ok)
    const haystack = `${item.model || ''} ${item.platform_key || ''} ${acctName(item)} ${item.account_id ?? ''}`.toLocaleLowerCase()
    const searchMatch = !needle || haystack.includes(needle)
    return statusMatch && searchMatch
  })
})
watch([statusFilter, query], () => { page.value = 1 })
const successCount = computed(() => logs.value.filter((item) => Boolean(item.ok)).length)
const failureCount = computed(() => logs.value.length - successCount.value)

function acctName(item) {
  const id = item?.account_id
  if (id == null) return '—'
  return accountMap.value.get(id) || String(id)
}

function acctInitials(item) {
  const name = acctName(item)
  if (!name || name === '—') return '·'
  return name.slice(0, 2)
}

function formatDur(ms) {
  if (ms == null) return '—'
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  return n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${Math.round(n)} ms`
}

function modelLabel(item) {
  const model = item?.model || ''
  const key = item?.platform_key || ''
  return model.startsWith(`${key}/`) ? model.slice(key.length + 1) || model : model
}

function modelSub(item) {
  const key = item?.platform_key || ''
  return key && item?.model && item.model.startsWith(`${key}/`) ? key : ''
}

function truncate(value) {
  const text = value || '—'
  return text.length > 60 ? `${text.slice(0, 60)}…` : text
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const [logsRes, acctRes] = await Promise.allSettled([getLogs({ limit: 500 }), getAccounts()])
    if (logsRes.status !== 'fulfilled') throw new Error(logsRes.reason?.response?.data?.detail || logsRes.reason?.message || '接口未能返回请求日志')
    const r = logsRes.value
    if (!r?.ok) throw new Error('接口未能返回请求日志')
    logs.value = Array.isArray(r.items) ? r.items : []
    if (page.value > pageCount.value) page.value = pageCount.value
    if (acctRes.status === 'fulfilled' && acctRes.value?.ok && Array.isArray(acctRes.value.items)) {
      accountMap.value = new Map(acctRes.value.items.map((a) => [a.id, a.name]))
    } else {
      accountMap.value = new Map()
    }
    toastOk('请求日志已刷新')
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '读取请求日志失败'
    toastErr('读取请求日志失败：' + error.value)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.view-wrap { min-width: 0; max-width: 100%; }
.search { margin-left: auto; min-width: 0; }
.search .input { width: min(260px, 100%); }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 32px 16px; color: var(--text-3); text-align: center; }
.empty-state strong { color: var(--text-2); font-size: 13px; }

.time-cell { white-space: nowrap; font-size: 11.5px; }
.model-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-cell .model-sub { margin-left: 6px; font-size: 10.5px; }
.req-acct { max-width: 170px; }
.req-acct .acct-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dur { min-width: 64px; white-space: nowrap; }
.error-cell { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

@media (max-width: 767px) {
  .search { flex: 1 1 100%; margin-left: 0; }
  .search .input { width: 100%; min-width: 0; }
  .tbl { min-width: 780px; }
}
</style>
