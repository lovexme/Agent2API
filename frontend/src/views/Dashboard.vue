<template>
  <div class="dashboard-view">
    <div class="page-head">
      <div><div class="page-title">总览</div><div class="page-desc">所有平台账号与网关活动一目了然</div></div>
      <div class="head-actions"><button class="btn ghost" @click="load">↻ 刷新</button></div>
    </div>
    <div v-loading="loading" class="dashboard-body">
      <div class="kpis">
        <div class="card kpi"><div class="kpi-label">账号总数</div><div class="kpi-value">{{ stats.total_accounts || 0 }}</div><div class="kpi-foot"><span class="trend up">{{ enabledAccounts }} 个启用</span></div></div>
        <div class="card kpi"><div class="kpi-label">活跃账号</div><div class="kpi-value">{{ stats.active_accounts || 0 }}</div><div class="kpi-foot"><span class="trend up">占全部 {{ pctActive }}%</span></div></div>
        <div class="card kpi"><div class="kpi-label">今日请求</div><div class="kpi-value">{{ stats.requests_today || 0 }}</div><div class="kpi-foot">经统一网关</div></div>
        <div class="card kpi"><div class="kpi-label">今日错误</div><div class="kpi-value">{{ stats.errors_today || 0 }}</div><div class="kpi-foot"><span class="trend" :class="errCls">{{ errRate }}% 错误率</span></div></div>
      </div>
      <div class="cols-2 dashboard-section">
        <div class="card"><div class="card-head">平台健康 <span class="muted dashboard-head-note">{{ connectedPlatforms }} 个平台接入</span></div><div class="card-body tight rank-list">
          <div v-for="(p, index) in platforms" :key="p.id" class="rank-row"><span class="rank-idx">{{ String(index + 1).padStart(2, '0') }}</span><div class="rank-main"><div class="rank-name">{{ p.name }}</div><div class="rank-sub">{{ p.account_count ? `${p.active_count} / ${p.account_count} 个账号有效` : '尚未接入账号' }}</div></div><div class="rank-bar"><div class="bar" :class="platformBar(p)"><i :style="p.avg_quota_pct != null ? { width: Math.min(p.avg_quota_pct, 100) + '%' } : {}"></i></div></div></div>
          <div v-if="!platforms.length" class="empty-row">暂无平台数据</div>
        </div></div>
        <div class="card"><div class="card-head">平台使用分布</div><div class="card-body tight rank-list">
          <div v-for="(p, index) in platforms" :key="`usage-${p.id}`" class="rank-row"><span class="rank-idx">{{ String(index + 1).padStart(2, '0') }}</span><div class="rank-main"><div class="rank-name">{{ p.name }}</div><div class="rank-sub">平均积分用量 {{ p.avg_quota_pct != null ? p.avg_quota_pct.toFixed(1) + '%' : '—' }}</div></div><span class="chip">{{ p.account_count || 0 }} 账号</span></div>
          <div v-if="!platforms.length" class="empty-row">暂无平台数据</div>
        </div></div>
      </div>
      <div class="card dashboard-section"><div class="card-head">最近请求 <router-link :to="'/gateway'" class="muted dashboard-link">查看网关 →</router-link></div>
        <div v-if="logs.length" class="card-body tight"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>平台</th><th>模型</th><th>结果</th><th class="r">耗时</th></tr></thead><tbody><tr v-for="l in logs" :key="l.id"><td class="muted">{{ l.created_at }}</td><td>{{ l.platform_key }}</td><td>{{ l.model }}</td><td><span :class="l.ok ? 'badge ok' : 'badge err'">{{ l.ok ? '✓ 成功' : '✗ ' + (l.err ? short(l.err) : '失败') }}</span></td><td class="r num muted">{{ l.latency_ms }} ms</td></tr></tbody></table></div></div>
        <div v-else-if="!loading" class="empty-state"><strong>暂无请求记录</strong><span>通过统一网关调用模型后，这里会显示请求流水</span></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getOverview, getLogs } from '../api'
import { toastErr } from '../lib/toast'

const data = ref({ platforms: [], stats: {}, gateway: {} })
const logs = ref([])
const loading = ref(false)

const platforms = computed(() => data.value.platforms || [])
const stats = computed(() => data.value.stats || {})
const connectedPlatforms = computed(() => platforms.value.filter((p) => p.account_count).length)
const enabledAccounts = computed(() => platforms.value.reduce((s, p) => s + (p.enabled_account_count || 0), 0))
const pctActive = computed(() => {
  const t = stats.value.total_accounts
  return t ? Math.round((stats.value.active_accounts / t) * 100) : 0
})
const errRate = computed(() => {
  const t = stats.value.requests_today
  return t ? ((stats.value.errors_today / t) * 100).toFixed(1) : 0
})
const errCls = computed(() => (errRate.value >= 5 ? 'bad' : errRate.value > 0 ? 'warn' : 'good'))

const PLAT_LOGO = { 'tabbit-domestic': 'dom', 'tabbit-intl': 'intl', 'loomy': 'loomy', 'trae': 'trae', 'workbuddy': 'work' }
const logoClass = (key) => PLAT_LOGO[key] || 'generic'
const logoText = (key) => (key.startsWith('tabbit') ? 'TB' : key === 'loomy' ? 'L' : key === 'trae' ? 'T' : key === 'workbuddy' ? 'W' : key.slice(0, 2).toUpperCase())
function platformBar(p) {
  if (!p.active_count || p.avg_quota_pct == null) return 'na'
  if (p.avg_quota_pct < 50) return ''
  if (p.avg_quota_pct <= 80) return 'mid'
  return 'high'
}
const short = (s) => (s.length > 40 ? s.slice(0, 40) + '…' : s)

async function load() {
  loading.value = true
  try {
    const [ov, lg] = await Promise.all([getOverview(), getLogs({ limit: 8 })])
    data.value = ov
    logs.value = lg.items || []
  } catch (e) {
    toastErr('加载总览失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.dashboard-body { min-height: 240px; }
.dashboard-section { margin-top: 12px; }
.dashboard-head-note { margin-left: auto; font-weight: 400; }
.dashboard-link { margin-left: auto; font-size: 12px; font-weight: 400; }
.empty-row { padding: 18px 16px; color: var(--text-3); text-align: center; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 34px 16px; color: var(--text-3); }
.empty-state strong { color: var(--text-2); font-size: 13px; }
@media (max-width: 767px) { .dashboard-head-note { width: 100%; margin-left: 0; } }
</style>