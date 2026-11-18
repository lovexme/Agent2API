<template>
  <div class="view-wrap"><div class="page-head"><div><div class="page-title">设置</div><div class="page-desc">面板安全 / 网关 / 自动化</div></div><div class="head-actions"><button class="btn primary" type="button" :disabled="saving || !loaded" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button></div></div>
    <div class="cols-2"><div class="card"><div class="card-head">面板与网关</div><div class="card-body tight"><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">面板管理密钥</div><div class="setting-desc">登录面板与管理接口使用，修改后需用新密钥登录</div></div><input v-model="panel_key" class="input setting-input" type="password" autocomplete="new-password" placeholder="已设置（留空不修改）" /></div><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">网关密钥</div><div class="setting-desc">调用 /v1 接口时作为 Bearer 请求头，修改后立即生效</div></div><input v-model="gateway_key" class="input setting-input" type="password" autocomplete="new-password" placeholder="已设置（留空不修改）" /></div><div class="setting-row"><div class="setting-info"><div class="setting-title">每日自动检测全部账号</div><div class="setting-desc">每天 08:00 由面板内调度器检测账号状态与积分(双实例自动去重)</div></div><button class="switch" :class="{ on: dailyCheck }" type="button" role="switch" :aria-checked="dailyCheck" @click="dailyCheck = !dailyCheck"><span></span></button></div><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">检测汇总 Webhook(可选)</div><div class="setting-desc">填写后每日检测汇总会 POST 到该地址;留空则只在面板记录,不推送</div></div><input v-model="notifyWebhook" class="input setting-input" type="url" placeholder="https://example.com/webhook(留空 = 不推送)" /></div><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">自动检测时间</div><div class="setting-desc">上次:{{ lastRunAt || '尚未运行' }}{{ summaryText ? ' · ' + summaryText : '' }}</div></div><span class="mono setting-value">下次 {{ nextRunAt || '—' }}</span></div><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">请求日志</div><div class="setting-desc">清空 request_log(网关页面与总览统计随之归零;账号与密钥不受影响)</div></div><div class="run-actions"><button class="btn sm" type="button" :disabled="running" @click="runNow">{{ running ? '检测中...' : '立即检测一次' }}</button><button class="btn ghost sm danger" type="button" :disabled="clearing" @click="clearLogsNow">{{ clearing ? '清理中...' : '清理日志' }}</button></div></div></div></div>
      <div class="card"><div class="card-head">运行信息</div><div class="card-body tight"><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">面板地址</div><div class="setting-desc">当前管理面板访问入口</div></div><span class="mono setting-value">{{ origin }}/</span></div><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">数据存储</div><div class="setting-desc">本机 SQLite 数据文件</div></div><span class="mono setting-value">data/aam.db（项目目录内）</span></div><div class="setting-row setting-field"><div class="setting-info"><div class="setting-title">IPv6 访问</div><div class="setting-desc">后端双栈监听状态</div></div><span class="badge ok">已启用</span></div></div><div class="card-body runtime-note">请求日志自动累积记录平台、模型、成败与耗时，用于网关页面与总览统计。账号凭据仅存储在本机 SQLite，不回传、不落日志。</div></div></div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getSettings, saveSettings, clearLogs, runAutoCheck } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const panel_key = ref('')
const gateway_key = ref('')
const saving = ref(false)
const loaded = ref(false)
const dailyCheck = ref(true)
const notifyWebhook = ref('')
const lastRunAt = ref('')
const nextRunAt = ref('')
const summaryText = ref('')
const clearing = ref(false)
const running = ref(false)
const origin = computed(() => window.location.origin)

async function load() {
  try {
    const s = await getSettings()
    panel_key.value = ''
    gateway_key.value = ''
    dailyCheck.value = (s.daily_auto_check || 'on') !== 'off'
    notifyWebhook.value = s.notify_webhook || ''
    lastRunAt.value = s.auto_check_last_at || ''
    nextRunAt.value = s.auto_check_next_at || ''
    summaryText.value = summaryLabel(s.auto_check_summary)
    loaded.value = true
  } catch (e) {
    toastErr('读取设置失败：' + (e.response?.data?.detail || e.message))
  }
}

async function save() {
  if (!loaded.value) return
  const payload = { daily_auto_check: dailyCheck.value ? 'on' : 'off', notify_webhook: notifyWebhook.value.trim() }
  if (panel_key.value.trim()) payload.panel_key = panel_key.value.trim()
  if (gateway_key.value.trim()) payload.gateway_key = gateway_key.value.trim()
  saving.value = true
  try {
    await saveSettings(payload)
    toastOk('设置已保存')
    await load()
  } catch (e) {
    toastErr('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

function summaryLabel(raw) {
  if (!raw) return ''
  try {
    const data = JSON.parse(raw)
    return `有效 ${data.active ?? 0} / 过期 ${data.expired ?? 0} / 错误 ${data.error ?? 0}${data.pushed ? ' · 已推送' : ''}`
  } catch { return '' }
}

async function runNow() {
  running.value = true
  try {
    const r = await runAutoCheck()
    toastOk(`检测完成:共 ${r.total} 个账号,有效 ${r.active} / 过期 ${r.expired} / 错误 ${r.error}`)
    await load()
  } catch (e) {
    toastErr('检测失败:' + (e.response?.data?.detail || e.message))
  } finally {
    running.value = false
  }
}

async function clearLogsNow() {
  try {
    await ElMessageBox.confirm('确定清空全部请求日志吗?网关页面与总览统计(今日请求/错误数)会归零,账号与密钥不受影响。', '清理日志确认', { confirmButtonText: '清理', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  clearing.value = true
  try {
    const r = await clearLogs()
    toastOk(`已清理 ${r.deleted} 条请求日志`)
  } catch (e) {
    toastErr('清理失败:' + (e.response?.data?.detail || e.message))
  } finally {
    clearing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.setting-field{align-items:flex-start}.run-actions{display:flex;gap:8px;flex:0 0 auto}.setting-input{width:min(240px,42%);flex:0 0 auto;margin-top:1px}.setting-value{width:min(240px,42%);flex:0 0 auto;color:var(--text-2);overflow-wrap:anywhere;text-align:right}.runtime-note{color:var(--text-2);font-size:12px;line-height:1.7;border-top:1px solid var(--border)}.switch span{position:absolute;inset:2px auto auto 2px;width:15px;height:15px;border-radius:999px;background:var(--text-3);transition:transform .15s,background .15s}.switch.on span{transform:translateX(17px);background:#fff}@media(max-width:640px){.setting-field{flex-wrap:wrap}.setting-input,.setting-value{width:100%;flex-basis:100%;margin-top:5px;text-align:left}}
</style>
