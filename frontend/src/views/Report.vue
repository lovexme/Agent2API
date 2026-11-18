<template>
  <div class="view-wrap report-view">
    <div class="page-head">
      <div>
        <div class="page-title">报表</div>
        <div class="page-desc">请求用量统计 · 基于当前保留的请求明细</div>
      </div>
      <div class="head-actions">
        <button class="btn ghost" type="button" :disabled="loading" @click="load">{{ loading ? '加载中...' : '↻ 刷新' }}</button>
      </div>
    </div>

    <!-- 常驻统计口径提示 -->
    <div class="card report-note">
      <div class="card-body">
        <strong>统计口径</strong>
        <span>报表基于当前保留的请求明细统计;在网关页「清理明细」后,报表全部归零。</span>
        <router-link to="/gateway" class="report-note-link">前往网关 →</router-link>
      </div>
    </div>

    <!-- 时间范围切换 -->
    <div class="card report-range">
      <div class="filters">
        <div class="seg">
          <button v-for="r in RANGES" :key="r.key" type="button" :class="{ on: rangeKey === r.key }" @click="pickRange(r.key)">{{ r.label }}</button>
        </div>
        <template v-if="rangeKey === 'custom'">
          <input v-model="from" type="date" class="input" aria-label="开始日期" @change="load" />
          <span class="muted">至</span>
          <input v-model="to" type="date" class="input" aria-label="结束日期" @change="load" />
        </template>
        <span class="range-hint muted">{{ rangeHint }}</span>
      </div>
    </div>

    <div v-loading="loading" class="report-body">
      <div class="kpis">
        <div class="card kpi">
          <div class="kpi-label">总请求数</div>
          <div class="kpi-value">{{ overview.total_requests || 0 }}</div>
          <div class="kpi-foot">范围内累计请求</div>
        </div>
        <div class="card kpi">
          <div class="kpi-label">成功率</div>
          <div class="kpi-value">{{ rateText }}<small v-if="okCount">成功 {{ okCount }}</small></div>
          <div class="kpi-foot"><span class="trend" :class="rateCls">{{ okCount }} 成功 / {{ errCount }} 失败</span></div>
        </div>
        <div class="card kpi">
          <div class="kpi-label">活跃天数</div>
          <div class="kpi-value">{{ overview.active_days || 0 }}</div>
          <div class="kpi-foot">有请求记录的日期数</div>
        </div>
        <div class="card kpi">
          <div class="kpi-label">当前连续天数</div>
          <div class="kpi-value">{{ overview.streak_days || 0 }}</div>
          <div class="kpi-foot">连续有请求的天数</div>
        </div>
      </div>

      <!-- 空态:所选范围内无请求 -->
      <div v-if="showEmpty" class="card report-empty">
        <div class="empty-state">
          <strong>所选范围内暂无请求</strong>
          <span>调整时间范围,或通过网关发起请求后再查看报表。</span>
        </div>
      </div>

      <template v-else>
        <!-- 趋势图(纯 CSS 柱状) -->
        <div class="card report-trend">
          <div class="card-head">
            <span>请求趋势</span>
            <span class="muted report-head-note">{{ rangeLabel }} · 共 {{ trend.length }} 个时间桶</span>
          </div>
          <div class="card-body">
            <div v-if="trend.length" class="chart">
              <div v-for="(b, i) in trend" :key="b.bucket" class="col" :title="tip(b)">
                <div class="col-track">
                  <div class="col-stack" :style="{ height: barHeight(b) }">
                    <div v-if="b.err" class="seg err" :style="{ height: segHit(b.err, b) }"></div>
                    <div v-if="b.ok" class="seg ok" :style="{ height: segHit(b.ok, b) }"></div>
                  </div>
                </div>
                <div class="col-x">{{ showX(i) ? xLabel(b.bucket) : '' }}</div>
              </div>
            </div>
            <div v-else class="empty-state compact">
              <strong>所选范围内暂无请求</strong>
              <span>趋势图将在此展示</span>
            </div>
          </div>
        </div>

        <!-- Top 三栏 -->
        <div class="cols-3 report-tops">
          <div v-for="col in topCols" :key="col.title" class="card">
            <div class="card-head"><span>{{ col.title }}</span><span v-if="col.items.length" class="muted report-head-note">Top {{ col.items.length }}</span></div>
            <div class="card-body tight rank-list">
              <div v-for="(it, i) in col.items" :key="it.key" class="rank-row">
                <span class="rank-idx">{{ idx(i) }}</span>
                <div class="rank-main">
                  <div class="rank-name" :title="it.key">{{ it.key }}</div>
                  <div class="rank-sub">{{ it.value || 0 }} 次请求</div>
                </div>
                <div class="rank-bar">
                  <div class="bar"><i :style="{ width: barW(it.value, col.items) }"></i></div>
                </div>
              </div>
              <div v-if="!col.items.length" class="empty-row">暂无数据</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getReport } from '../api'
import { toastErr } from '../lib/toast'

const RANGES = [
  { key: 'm10', label: '近10分钟' },
  { key: 'h1', label: '近1小时' },
  { key: 'h24', label: '近24小时' },
  { key: 'd7', label: '近7天' },
  { key: 'd30', label: '近30天' },
  { key: 'month', label: '本月' },
  { key: 'custom', label: '自定义' }
]

const report = ref(null)
const loading = ref(false)
const rangeKey = ref('d7')

const pad = (n) => String(n).padStart(2, '0')
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

const today = new Date()
const from = ref(ymd(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6)))
const to = ref(ymd(today))

const overview = computed(() => report.value?.overview || {})
const trend = computed(() => report.value?.trend || [])
const total = computed(() => Number(overview.value.total_requests) || 0)
const okCount = computed(() => Number(overview.value.ok_requests) || 0)
const errCount = computed(() => Number(overview.value.err_requests) || 0)

const topCols = computed(() => {
  const t = report.value?.top || {}
  return [
    { title: 'Top 提供商', items: t.providers || [] },
    { title: 'Top 模型', items: t.models || [] },
    { title: 'Top 账号', items: t.accounts || [] }
  ]
})

const ratePct = computed(() => {
  const r = overview.value.success_rate
  if (r != null && !Number.isNaN(Number(r))) return Number(r) * 100
  return total.value ? (okCount.value / total.value) * 100 : 0
})
const rateText = computed(() => (total.value ? ratePct.value.toFixed(1) + '%' : '—'))
const rateCls = computed(() => (!total.value ? '' : ratePct.value >= 99 ? 'up' : ratePct.value < 90 ? 'down' : ''))

const showEmpty = computed(() => !loading.value && total.value === 0)

const curLabel = computed(() => (RANGES.find((r) => r.key === rangeKey.value) || {}).label || '')
const rangeLabel = computed(() => {
  const r = report.value?.range
  if (!r) return ''
  return [r.start, r.end].filter(Boolean).join(' ~ ')
})
const rangeHint = computed(() => [curLabel.value, rangeLabel.value].filter(Boolean).join(' · '))

function buildParams() {
  switch (rangeKey.value) {
    case 'm10': return { minutes: 10 }
    case 'h1': return { hours: 1 }
    case 'h24': return { hours: 24 }
    case 'd7': return { days: 7 }
    case 'd30': return { days: 30 }
    case 'month': {
      const n = new Date()
      return { start: ymd(new Date(n.getFullYear(), n.getMonth(), 1)), end: ymd(n) }
    }
    case 'custom': {
      const p = {}
      if (from.value) p.start = from.value
      if (to.value) p.end = to.value
      return p
    }
    default: return { days: 7 }
  }
}

function pickRange(key) {
  if (rangeKey.value === key) return
  rangeKey.value = key
  load()
}

async function load() {
  loading.value = true
  try {
    const d = await getReport(buildParams())
    report.value = d && typeof d === 'object' ? d : null
  } catch (e) {
    toastErr('加载报表失败:' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

// ── 趋势图(纯 CSS,按最大值归一化) ──
const bucketTotal = (b) => (Number(b.ok) || 0) + (Number(b.err) || 0)
const maxBucket = computed(() => trend.value.reduce((m, b) => Math.max(m, bucketTotal(b)), 0) || 1)
function barHeight(b) {
  const t = bucketTotal(b)
  if (!t) return '0%'
  return Math.max(2, (t / maxBucket.value) * 100) + '%'
}
function segHit(v, b) {
  const t = bucketTotal(b)
  return t ? (Number(v) || 0) / t * 100 + '%' : '0%'
}
function tip(b) {
  return `${b.bucket} · 成功 ${Number(b.ok) || 0} / 失败 ${Number(b.err) || 0}`
}
function xLabel(bucket) {
  const s = String(bucket || '')
  if (s.length >= 16) return s.slice(11, 16)
  if (s.length >= 10) return s.slice(5)
  return s
}
function showX(i) {
  const n = trend.value.length
  if (n <= 16) return true
  const step = Math.ceil(n / 8)
  return i % step === 0 || i === n - 1
}

// ── Top 排行 ──
const idx = (i) => String(i + 1).padStart(2, '0')
function barW(v, items) {
  const max = items.reduce((m, it) => Math.max(m, Number(it.value) || 0), 0) || 1
  return Math.round(((Number(v) || 0) / max) * 100) + '%'
}

onMounted(load)
</script>

<style scoped>
.report-body { min-height: 240px; }
.report-note { margin-bottom: 12px; background: color-mix(in oklab, var(--primary) 6%, var(--surface)); border-color: color-mix(in oklab, var(--primary) 22%, var(--border)); }
.report-note .card-body { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12px; color: var(--text-2); }
.report-note strong { color: var(--text); font-size: 12px; }
.report-note-link { margin-left: auto; font-size: 12px; }
.report-range { margin-bottom: 12px; }
.report-range .filters { border-bottom: 0; }
.range-hint { margin-left: auto; font-size: 11.5px; }
.report-head-note { margin-left: auto; font-size: 11.5px; font-weight: 400; }
.report-empty, .report-trend, .report-tops { margin-top: 12px; }

/* ── 纯 CSS 柱状趋势图 ── */
.chart { display: flex; align-items: flex-end; gap: 4px; height: 200px; }
.col { flex: 1 1 0; min-width: 3px; height: 100%; display: flex; flex-direction: column; }
.col-track { flex: 1 1 auto; display: flex; align-items: flex-end; min-height: 0; }
.col-stack { width: 100%; display: flex; flex-direction: column; justify-content: flex-end; border-radius: 3px 3px 0 0; overflow: hidden; background: var(--surface-2); }
.seg { width: 100%; flex: 0 0 auto; }
.seg.ok { background: var(--primary); }
.seg.err { background: var(--danger); }
.col:hover .col-stack { filter: brightness(1.12); }
.col-x { height: 16px; margin-top: 5px; font-size: 10px; line-height: 16px; color: var(--text-3); text-align: center; white-space: nowrap; overflow: hidden; font-variant-numeric: tabular-nums; }

.empty-row { padding: 18px 16px; color: var(--text-3); text-align: center; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 38px 16px; color: var(--text-3); text-align: center; }
.empty-state strong { color: var(--text-2); font-size: 13px; }
.empty-state.compact { padding: 30px 16px; }

@media (max-width: 900px) {
  .range-hint { margin-left: 0; }
}
</style>
