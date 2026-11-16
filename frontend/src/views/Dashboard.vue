<template>
  <div>
    <div class="heading">
      <div>
        <div class="eyebrow">账户群健康度</div>
        <h1>总览</h1>
        <div class="sub">所有平台账号与网关活动一目了然</div>
      </div>
      <button class="btn secondary sm" @click="load">↻ 刷新</button>
    </div>

    <div v-loading="loading" style="min-height: 240px">
      <div class="kpis" style="margin-bottom: 14px">
        <div class="kpi">
          <div class="kpi-top">账号总数 <span>01</span></div>
          <strong>{{ stats.total_accounts || 0 }}</strong>
          <span class="delta">{{ enabledAccounts }} 个启用</span>
        </div>
        <div class="kpi">
          <div class="kpi-top">活跃账号 <span>02</span></div>
          <strong>{{ stats.active_accounts || 0 }}</strong>
          <span class="delta good">占全部 {{ pctActive }}%</span>
        </div>
        <div class="kpi">
          <div class="kpi-top">今日请求 <span>03</span></div>
          <strong>{{ stats.requests_today || 0 }}</strong>
          <span class="delta">经统一网关</span>
        </div>
        <div class="kpi">
          <div class="kpi-top">今日错误 <span>04</span></div>
          <strong>{{ stats.errors_today || 0 }}</strong>
          <span class="delta" :class="errCls">{{ errRate }}% 错误率</span>
        </div>
      </div>

      <div class="section-head"><h2>平台健康</h2><span class="muted">{{ connectedPlatforms }} 个平台接入</span></div>
      <div class="platforms">
        <div v-for="p in platforms" :key="p.id" class="platform">
          <div class="platform-head">
            <div class="platform-title"><span class="logo" :class="logoClass(p.key)">{{ logoText(p.key) }}</span>{{ p.name }}</div>
            <span class="state" :class="p.account_count ? (p.active_count ? 'active-state' : 'unknown-state') : 'unknown-state'">
              {{ p.account_count ? p.active_count + ' 个有效' : '未接入' }}
            </span>
          </div>
          <p v-if="p.account_count">共 {{ p.account_count }} 个账号 · 平均积分用量</p>
          <p v-else>尚未添加账号 · 请到「账号管理」接入</p>
          <div class="minirow"><span>平均用量</span><b>{{ p.avg_quota_pct != null ? p.avg_quota_pct.toFixed(1) + '%' : '—' }}</b></div>
          <div class="bar"><i :class="platformBar(p)" :style="p.avg_quota_pct != null ? { width: Math.min(p.avg_quota_pct, 100) + '%' } : {}"></i></div>
        </div>
      </div>

      <div class="section-head">
        <h2>最近请求</h2>
        <router-link :to="'/gateway'" class="muted" style="font-size: 12px">查看网关 →</router-link>
      </div>
      <div class="table-wrap" v-if="logs.length">
        <table class="table">
          <thead><tr><th>时间</th><th>平台</th><th>模型</th><th>结果</th><th>耗时</th></tr></thead>
          <tbody>
            <tr v-for="l in logs" :key="l.id">
              <td class="muted">{{ l.created_at }}</td>
              <td>{{ l.platform_key }}</td>
              <td>{{ l.model }}</td>
              <td><span :class="l.ok ? 'ok' : 'fail'">{{ l.ok ? '✓ 成功' : '✗ ' + (l.err ? short(l.err) : '失败') }}</span></td>
              <td class="muted">{{ l.latency_ms }} ms</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!loading" class="empty"><h3>暂无请求记录</h3><p>通过统一网关调用模型后，这里会显示请求流水</p></div>
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
const enabledAccounts = computed(() => platforms.value.reduce((s, p) => s + p.account_count, 0))
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