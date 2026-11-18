<template>
  <section class="accounts-view">
    <header class="page-head">
      <div><div class="page-title">账号池</div><div class="page-desc">多平台账号统一管理 · 状态、积分与凭据一览</div></div>
      <div class="head-actions">
        <button class="btn" @click="openTraeLogin">Trae 浏览器登录</button><button class="btn" @click="openWorkbuddyLogin">WorkBuddy 授权</button><button class="btn" @click="openSmsLogin">手机验证码添加</button><button class="btn" @click="openDailyTasks">每日任务</button><button class="btn primary" @click="openCreate">＋ 新增账号</button>
      </div>
    </header>
    <div class="card">
      <div class="filters">
        <div class="seg platform-seg"><button :class="{ on: !platformFilter }" @click="platformFilter = ''; reload()">全部平台</button><button v-for="p in platforms" :key="p.id" :class="{ on: String(platformFilter) === String(p.id) }" @click="platformFilter = p.id; reload()">{{ p.name }}</button></div>
        <div class="seg status-seg"><button :class="{ on: !statusFilter }" @click="statusFilter = ''; reload()">全部状态</button><button v-for="s in [{id:'active',name:'有效'},{id:'expired',name:'过期'},{id:'error',name:'异常'},{id:'unknown',name:'未检查'},{id:'disabled',name:'已禁用'}]" :key="s.id" :class="{ on: statusFilter === s.id }" @click="statusFilter = s.id; reload()">{{ s.name }}</button></div>
        <div class="search"><input class="input" v-model="q" placeholder="搜索账号名 / 平台 / 用户 ID" @input="reload" /></div><button class="btn ghost sm" @click="resetFilters">重置筛选</button>
      </div>
      <div v-if="selected.length" class="batch-bar"><span>已选 <strong>{{ selected.length }}</strong> / {{ items.length }} 个账号</span><button class="btn sm" type="button" :disabled="batchBusy" @click="batchCheck">{{ batchBusy ? '处理中...' : '批量检测' }}</button><button class="btn sm danger" type="button" :disabled="batchBusy" @click="batchDelete">批量删除</button><button class="btn ghost sm" type="button" @click="selected = []">取消选择</button></div>
      <div v-loading="loading" class="tbl-wrap"><table class="tbl"><thead><tr><th class="c"><input type="checkbox" aria-label="选择全部账号" :checked="allSelected" :indeterminate.prop="someSelected" @change="toggleAll" /></th><th>账号</th><th>平台</th><th>状态</th><th>等级</th><th>积分进度</th><th>到期</th><th class="r">请求数</th><th>操作</th></tr></thead><tbody>
        <tr v-for="a in pageItems" :key="a.id">
          <td class="c"><input type="checkbox" :value="a.id" v-model="selected" :aria-label="`选择 ${a.name}`" /></td>
          <td><div class="acct-cell"><span class="avatar" :class="logoClass(a.platform_key)">{{ logoText(a.platform_key) }}</span><div class="acct-copy"><div class="acct-name" :title="a.name">{{ a.name }}</div><div class="acct-meta">{{ a.platform_name }}{{ a.user_info && a.user_info.secret_mobile ? ` · ${a.user_info.secret_mobile}` : '' }}{{ a.user_info ? ` · ${shortId(a)}` : '' }}</div></div></div></td>
          <td><span class="chip" :class="a.platform_key === 'tabbit-intl' ? 'intl' : 'cn'">{{ a.platform_name }}</span></td>
          <td><span class="badge" :class="a.status === 'active' ? 'ok' : ['expired','error'].includes(a.status) ? 'err' : a.status === 'unknown' ? 'dim' : 'warn'"><span class="dot"></span>{{ statusText(a) }}</span></td>
          <td><span v-if="a.member_level" class="badge blue">{{ a.member_level.toUpperCase() }}</span><span v-else class="muted">—</span></td>
          <td class="quota-cell"><div class="quota-line"><span>{{ quotaText(a) }}</span><span v-if="sessionDays(a) !== null" class="acct-meta">剩 {{ sessionDays(a) }} 天</span></div><div class="bar" :class="barClass(a)"><i :style="barStyle(a)"></i></div><div class="acct-meta">{{ resetText(a) }}</div></td>
          <td><span class="acct-meta">{{ sessionDays(a) !== null ? `${sessionDays(a)} 天` : (isWb(a) && (a.quota_json || {}).credits_earliest_expiry ? (a.quota_json || {}).credits_earliest_expiry.slice(0, 10) : '—') }}</span></td><td class="r num">{{ a.request_count ?? a.requests ?? '—' }}</td>
          <td><div class="row-actions"><button class="btn ghost sm" :disabled="busy===a.id" @click="doCheck(a)">检测</button><button class="btn ghost sm" @click="showModels(a)">模型</button><button class="btn ghost sm" @click="openEdit(a)">编辑</button><button class="btn ghost sm danger" @click="doDelete(a)">删除</button></div></td>
        </tr>
        <tr v-if="!items.length && !loading"><td colspan="9"><div class="empty"><strong>还没有账号</strong><span>新增账号并填写凭据后，即可在此查看状态与额度。</span><button class="btn primary" @click="openCreate">＋ 新增账号</button></div></td></tr>
      </tbody></table></div>
      <div class="table-foot"><span>共 {{ total }} 个账号</span>
      <div class="pager">
        <button :disabled="page <= 1" @click="page--">‹</button>
        <template v-for="n in pageNumbers" :key="n">
          <button v-if="n === '…'" class="dim" disabled>…</button>
          <button v-else :class="{ on: n === page }" @click="page = n">{{ n }}</button>
        </template>
        <button :disabled="page >= pageCount" @click="page++">›</button>
        <span class="pg-size">每页
          <select class="select" v-model.number="pageSize" style="width:64px;height:26px;font-size:11px;">
            <option :value="15">15</option><option :value="30">30</option><option :value="50">50</option>
          </select>
        </span>
      </div></div>
    </div>
    <div v-if="dialog.show || models.show || dailyTasks.show || traeLogin.show || workbuddy.show || sms.show" class="mask open" @click.self="dialog.show = false; models.show = false; dailyTasks.show = false; workbuddy.show = false; traeLogin.show = false; sms.show = false; closeTraeLogin(); stopWorkbuddyPolling()"></div>
    <section v-if="dialog.show" class="modal open" role="dialog" aria-modal="true"><header class="modal-head">{{ dialog.mode === 'create' ? '新增账号' : '编辑账号' }}</header><div class="modal-body"><div class="tabs"><button type="button" :class="{ on: dialog.tab !== 'help' }" @click="dialog.tab = 'cred'">账号凭据</button><button type="button" :class="{ on: dialog.tab === 'help' }" @click="dialog.tab = 'help'">凭据说明</button></div><template v-if="dialog.tab !== 'help'"><div class="field"><label>所属平台</label><select class="select" v-model="dialog.platform_id" :disabled="dialog.mode === 'edit'"><option v-for="p in platforms" :key="p.id" :value="p.id">{{ p.name }}（{{ p.key }}）</option></select></div><div class="field"><label>备注名</label><input class="input" v-model="dialog.name" placeholder="如：国内主号" /></div><div class="field"><label>凭据输入方式</label><div class="seg credential-tabs"><button v-for="mode in credentialModesFor" :key="mode.id" type="button" :class="{ on: dialog.credentialMode === mode.id }" @click="dialog.credentialMode = mode.id">{{ mode.label }}</button></div><div class="hint" style="margin-top:-2px">已按当前平台自动限定可用方式</div></div><div class="field credential-field"><label>凭据内容</label><textarea v-if="dialog.credentialMode === 'cookie' || dialog.credentialMode === 'json'" class="input textarea" v-model="dialog.credential" rows="5" :placeholder="dialog.credentialMode === 'json' ? '粘贴完整 JSON 凭据' : credentialPlaceholder"></textarea><input v-else-if="dialog.credentialMode === 'token'" class="input" v-model="dialog.credential" type="password" autocomplete="off" placeholder="粘贴 Access Token / API Key / Session Token" /><div v-else class="browser-guide"><strong>浏览器登录引导</strong><p>登录完成后复制会话凭据，并切换到 Cookie 或 Token 方式提交。</p></div><span class="hint">{{ credentialHint }}</span></div></template><div v-else class="cred-help"><strong>{{ credHelp.title }}</strong><ol><li v-for="(step, i) in credHelp.steps" :key="i">{{ step }}</li></ol><p class="hint">{{ credHelp.hint }}</p><p class="hint">提交后面板会立即对账号做一次真实检测,状态与积分以检测结果为准。</p></div></div><footer class="modal-foot"><button class="btn" @click="dialog.show = false">取消</button><button class="btn primary" :disabled="saving" @click="save">{{ saving ? '保存并检测中…' : '保存并自动检测' }}</button></footer></section>
    <section v-if="models.show" class="modal open" role="dialog" aria-modal="true"><header class="modal-head">可用模型 · {{ models.name }}</header><div class="modal-body"><div v-if="!models.items.length" class="empty"><strong>暂无模型数据</strong><span>重新加载该账号的模型列表。</span></div><div v-else class="model-list"><span v-for="m in models.items" :key="m" class="chip">{{ m }}</span></div></div><footer class="modal-foot"><button class="btn" @click="models.show = false">关闭</button><button class="btn primary" :disabled="models.loading" @click="reloadModels">{{ models.loading ? '加载中…' : '重新加载' }}</button></footer></section>
    <section v-if="dailyTasks.show" class="modal open wide" role="dialog" aria-modal="true"><header class="modal-head">每日任务</header><div class="modal-body"><p class="task-tip">Trae 签到状态来自账号列表，可单个执行或全部签到。</p><div v-if="dailyTasks.loading" class="muted">正在加载 Trae 账号…</div><div v-else-if="!dailyTasks.items.length" class="empty"><strong>暂无 Trae 账号</strong><span>Trae 网关账号列表为空。</span></div><div v-else class="daily-task-list"><div v-for="task in dailyTasks.items" :key="task.account_id" class="daily-task-row"><div class="task-account"><strong>{{ task.label || task.account_id }}</strong><span class="acct-meta">{{ task.user_id || task.account_id }}</span></div><span class="badge" :class="task.ok === true ? 'ok' : task.ok === false ? 'err' : 'dim'">{{ task.message || '待签到' }}</span><button class="btn sm" :disabled="dailyTasks.busy" @click="checkinTask(task)">{{ dailyTasks.busyId === task.account_id ? '签到中…' : '签到' }}</button></div></div></div><footer class="modal-foot"><button class="btn" :disabled="dailyTasks.loading || dailyTasks.busy" @click="loadDailyTasks">刷新状态</button><button class="btn" @click="dailyTasks.show = false">关闭</button><button class="btn primary" :disabled="dailyTasks.loading || dailyTasks.busy || !dailyTasks.items.length" @click="checkinAllTasks">{{ dailyTasks.busy ? '签到中…' : '全部签到' }}</button></footer></section>
    <section v-if="traeLogin.show" class="modal open wide" role="dialog" aria-modal="true"><header class="modal-head">Trae 账号授权 <span class="badge" :class="traeLogin.boxUp ? 'ok' : 'warn'">{{ traeLogin.boxUp ? '服务就绪' : '沙箱未启动' }}</span><span class="spacer"></span><span class="acct-meta">已保存 {{ traeLogin.count }} 个账号</span></header><div class="modal-body"><p class="task-tip">下载并运行本机授权助手，再打开 Trae 授权页完成登录；凭据会自动推送至服务器。</p><ol class="oauth-steps"><li>下载授权助手：<a :href="helperLink('bat')" download>Windows .bat</a> · <a :href="helperLink('sh')" download>Mac/Linux .sh</a> · <a :href="helperLink('py')" download>通用 .py</a></li><li>运行助手并保持窗口开启。</li><li>打开授权页登录，完成后账号池会自动刷新。</li></ol><details><summary>备选：沙箱实时画面</summary><div class="trae-login-wrap"><iframe v-if="traeLogin.show" :src="traeLogin.url" class="trae-login-frame" allow="clipboard-read; clipboard-write"></iframe></div></details></div><footer class="modal-foot"><button class="btn" @click="resetSandbox">重置沙箱</button><button class="btn" @click="openAuthPage">打开授权页</button><button class="btn primary" @click="traeLogin.show = false; closeTraeLogin()">关闭</button></footer></section>
    <section v-if="workbuddy.show" class="modal open" role="dialog" aria-modal="true"><header class="modal-head">WorkBuddy 账号授权</header><div class="modal-body"><div class="field"><label>授权地址</label><a v-if="workbuddy.url" class="auth-link" :href="workbuddy.url" target="_blank" rel="noopener noreferrer">{{ workbuddy.url }}</a><span v-else class="muted">正在生成授权地址…</span><button v-if="workbuddy.url" class="btn sm" @click="copyWorkbuddyUrl">复制授权地址</button></div><p class="muted">{{ workbuddy.message || '请打开授权地址完成登录，本页面会自动检测。' }}</p></div><footer class="modal-foot"><button class="btn primary" @click="workbuddy.show = false; stopWorkbuddyPolling()">关闭</button></footer></section>
    <section v-if="sms.show" class="modal open" role="dialog" aria-modal="true"><header class="modal-head">手机验证码添加账号</header><div class="modal-body"><div class="field"><label>平台</label><select class="select" v-model="sms.platform_id"><option v-for="p in smsPlatforms" :key="p.id" :value="p.id">{{ p.name }}（{{ p.key }}）</option></select></div><div class="field"><label>手机号</label><input class="input" v-model="sms.phone" placeholder="输入接收验证码的手机号" /></div><div class="field"><label>短信验证码</label><div class="sms-code"><input class="input" v-model="sms.code" placeholder="输入验证码" /><button class="btn" :disabled="sms.sending || sms.timer > 0" @click="smsSend">{{ sms.timer > 0 ? `${sms.timer}s 后可重发` : (sms.sending ? '发送中…' : '发送验证码') }}</button></div></div><p v-if="sms.msg" class="sms-msg">{{ sms.msg }}</p></div><footer class="modal-foot"><button class="btn" @click="sms.show = false">取消</button><button class="btn primary" :disabled="sms.verifying" @click="smsVerify">{{ sms.verifying ? '验证并添加中…' : '验证并添加' }}</button></footer></section>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getAccounts, getPlatforms, createAccount, updateAccount, deleteAccount, checkAccount, getAccountModels } from '../api'
import { toastOk, toastErr } from '../lib/toast'
import { copyText } from '../lib/clipboard'

const items = ref([])
const page = ref(1)
const pageSize = ref(15)
const filteredItems = computed(() => items.value)
const total = computed(() => items.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const pageItems = computed(() => filteredItems.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
function pageNumbers() {
  const c = pageCount.value, cur = page.value, out = []
  for (let i = 1; i <= c; i++) {
    if (i === 1 || i === c || Math.abs(i - cur) <= 1) out.push(i)
    else if (out[out.length - 1] !== '…') out.push('…')
  }
  return out
}
const platforms = ref([])
const loading = ref(false)
const busy = ref(null)
const saving = ref(false)
const q = ref('')
const platformFilter = ref('')
const statusFilter = ref('')
const selected = ref([])
const batchBusy = ref(false)
const allSelected = computed(() => items.value.length > 0 && items.value.every((a) => selected.value.includes(a.id)))
const someSelected = computed(() => { const n = items.value.filter((a) => selected.value.includes(a.id)).length; return n > 0 && n < items.value.length })
function toggleAll(event) { selected.value = event.target.checked ? items.value.map((a) => a.id) : [] }

const dialog = ref({ show: false, mode: 'create', platform_id: null, name: '', credential: '', credentialMode: 'cookie' })
const credentialModes = [
  { id: 'cookie', label: 'Cookie' },
  { id: 'token', label: 'Token / API Key' },
  { id: 'json', label: 'JSON 凭据' },
  { id: 'browser', label: '浏览器登录引导' },
]
// 按平台自适应可用的凭据方式：不同平台只给出它真正支持的接入方式
// 优先用平台 key 区分（trae/workbuddy 同为 openai_compat 适配器，需 key 才分得开）
function modesForPlatform(p) {
  const key = String(p?.key || '').toLowerCase()
  const ad = String(p?.adapter || '').toLowerCase()
  const pick = (ids) => ids.map(id => credentialModes.find(m => m.id === id)).filter(Boolean)
  if (key.includes('tabbit') || ad === 'tabbit') return pick(['cookie', 'browser'])
  if (key === 'trae') return pick(['browser', 'cookie'])
  if (key === 'workbuddy') return pick(['browser', 'json'])
  if (key === 'loomy' || ad === 'loomy') return pick(['token', 'json'])
  if (ad === 'openai_compat') return pick(['token', 'json'])
  return credentialModes
}
const credentialModesFor = computed(() => modesForPlatform(currentPlatform.value))
// 编辑回填：'session' 与 token 同族，统一落到 Token 页签，保存时保留原值
function modeForAccount(a) {
  const p = platforms.value.find(x => x.id === a.platform_id) || {}
  const allowed = modesForPlatform(p).map(m => m.id)
  const orig = a.credential_type === 'session' ? 'token' : a.credential_type
  return allowed.includes(orig) ? orig : (allowed[0] || 'cookie')
}
// 切平台时同步修正凭据模式（保证落在该平台可用集合内）
watch(() => dialog.value.platform_id, () => {
  const allowed = credentialModesFor.value.map(m => m.id)
  if (!allowed.includes(dialog.value.credentialMode)) dialog.value.credentialMode = allowed[0] || 'cookie'
})
const models = ref({ show: false, items: [], name: '', accountId: null, loading: false })
const workbuddy = ref({ show: false, state: '', url: '', message: '', timer: null })
let workbuddyPollTimer = null
let traePollTimer = null
let smsCountdownTimer = null
function stopWorkbuddyPolling() {
  if (workbuddyPollTimer !== null) clearInterval(workbuddyPollTimer)
  workbuddyPollTimer = null
  workbuddy.value.timer = null
}
async function openWorkbuddyLogin() {
  stopWorkbuddyPolling()
  workbuddy.value = { show: true, state: '', url: '', message: '正在生成授权地址…', timer: null }
  try {
    const response = await fetch('/api/login/workbuddy/start', { method: 'POST' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.message || '授权地址生成失败')
    workbuddy.value.state = payload.state
    workbuddy.value.url = payload.url
    workbuddy.value.message = '请在授权页面完成登录，正在等待授权…'
    workbuddyPollTimer = setInterval(pollWorkbuddyStatus, 3000)
    workbuddy.value.timer = workbuddyPollTimer
    pollWorkbuddyStatus()
  } catch (error) {
    workbuddy.value.message = `授权初始化失败：${error.message}`
    toastErr('WorkBuddy 授权地址生成失败')
  }
}
async function pollWorkbuddyStatus() {
  const state = workbuddy.value.state
  if (!state || !workbuddy.value.show) return
  try {
    const response = await fetch(`/api/login/workbuddy/status?state=${encodeURIComponent(state)}`)
    const payload = await response.json()
    if (payload.status === 'done') {
      stopWorkbuddyPolling()
      workbuddy.value.message = `授权完成，账号 ${payload.account?.name || ''} 已添加`
      toastOk('WorkBuddy 授权完成，账号已入库')
      workbuddy.value.show = false
      await reload()
    } else if (payload.status === 'expired') {
      stopWorkbuddyPolling()
      workbuddy.value.message = payload.message || '授权已过期，请重新开始'
    } else if (!response.ok) {
      throw new Error(payload.detail || '状态查询失败')
    }
  } catch (error) {
    workbuddy.value.message = `状态查询失败：${error.message}`
  }
}
async function copyWorkbuddyUrl() {
  const ok = await copyText(workbuddy.value.url)
  if (ok) toastOk('授权地址已复制')
  else toastErr('复制失败，请手动复制链接')
}

// ── 手机验证码添加（发短信建号） ──
const smsPlatforms = computed(() => platforms.value.filter(p => ['loomy', 'tabbit-domestic', 'tabbit-intl'].includes(p.key)))
const sms = ref({ show: false, platform_id: null, phone: '', code: '', msgid: '', sent: false, sentKey: '', msg: '', timer: 0, sending: false, verifying: false, tick: null })
function openSmsLogin() {
  sms.value.show = true
  sms.value.platform_id = smsPlatforms.value[0]?.id || null
  sms.value.phone = ''
  sms.value.code = ''
  sms.value.msgid = ''
  sms.value.sent = false
  sms.value.msg = ''
}
async function smsSend() {
  const s = sms.value
  const ph = s.phone.trim()
  if (!s.platform_id) return toastErr('请先选平台')
  const key = smsPlatforms.value.find(p => p.id === s.platform_id)?.key
  const isIntl = key === 'tabbit-intl'
  if (isIntl) {
    if (!/^\+?\d{8,15}$/.test(ph)) return toastErr('国际版手机号格式：+8618900000000 或纯数字 8-15 位')
  } else if (!/^1\d{10}$/.test(ph)) return toastErr('手机号格式不对（11 位大陆号）')
  s.sending = true
  s.msg = '发送中…'
  try {
    const isTabbit = key === 'tabbit-domestic' || isIntl
    const url = isTabbit
      ? `/api/login/tabbit/send${isIntl ? '?platform=tabbit-intl' : ''}`
      : `/api/login/loomy/send?phone=${encodeURIComponent(ph)}`
    const r = await fetch(url, {
      method: 'POST',
      headers: isTabbit ? { 'Content-Type': 'application/json' } : {},
      body: isTabbit ? JSON.stringify({ phone: ph }) : undefined,
    })
    const j = await r.json()
    if (j.ok) {
      if (j.msgid) s.msgid = j.msgid
      s.sent = true
      s.sentKey = key
      s.msg = `✅ 验证码已发送到 ${ph}（5 分钟内有效）`
      toastOk('验证码已发送，请看手机')
      startSmsTimer(60)
    } else {
      const desc = (j.payload && (j.payload.desc || j.payload.msg)) || j.detail || j.message || '发送失败'
      s.msg = `❌ ${desc}`
      toastErr(`发码失败：${desc}`)
    }
  } catch (e) {
    s.msg = `❌ 网络错误：${e.message}`
    toastErr('发码请求失败')
  } finally {
    s.sending = false
  }
}
// 切换平台下拉时重置短信状态（msgid/sent/msgid/timer 残留会把 A 平台验证码污染到 B 平台）
watch(() => sms.value.platform_id, (nv, ov) => {
  if (nv === ov) return
  sms.value.msgid = ''
  sms.value.sent = false
  sms.value.sentKey = ''
  sms.value.msg = ''
  sms.value.code = ''
  sms.value.timer = 0
  if (smsCountdownTimer !== null) { clearInterval(smsCountdownTimer); smsCountdownTimer = null }
  sms.value.tick = null
})
function startSmsTimer(sec) {
  sms.value.timer = sec
  if (smsCountdownTimer !== null) clearInterval(smsCountdownTimer)
  smsCountdownTimer = setInterval(() => {
    sms.value.timer -= 1
    if (sms.value.timer <= 0) {
      clearInterval(smsCountdownTimer)
      smsCountdownTimer = null
      sms.value.tick = null
    }
  }, 1000)
  sms.value.tick = smsCountdownTimer
}
async function smsVerify() {
  const s = sms.value
  const ph = s.phone.trim()
  if (!s.sent) return toastErr('请先发送验证码')
  if (!s.code.trim()) return toastErr('请输入验证码')
  const key = smsPlatforms.value.find(p => p.id === s.platform_id)?.key
  if (s.sentKey && s.sentKey !== key) {
    s.sent = false; s.msgid = ''; s.msg = ''
    return toastErr('已切换平台，请为当前平台重新发送验证码')
  }
  const isIntl = key === 'tabbit-intl'
  if (!s.msgid && key !== 'tabbit-domestic' && !isIntl) return toastErr('发送接口未返回 msgid，请重新发送验证码')
  if (!['loomy', 'tabbit-domestic', 'tabbit-intl'].includes(key)) return toastErr('该平台暂不支持短信登录')
  const seg = (key === 'tabbit-domestic' || isIntl) ? 'tabbit' : key
  const qs = isIntl ? '?platform=tabbit-intl' : ''
  s.verifying = true
  s.msg = '验证中…'
  try {
    const r = await fetch(`/api/login/${seg}/verify${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: ph, mcode: s.code.trim(), msgid: s.msgid }),
    })
    const j = await r.json()
    if (j.ok) {
      s.msg = `✅ 添加成功：${j.account?.name || ''}（状态 ${j.account?.status || ''}）`
      toastOk('🎉 账号已添加并入库！')
      if (smsCountdownTimer !== null) clearInterval(smsCountdownTimer)
      smsCountdownTimer = null
      s.tick = null
      s.show = false
      await reload()
    } else {
      const desc = j.detail || '校验失败'
      s.msg = `❌ ${desc}`
      toastErr(desc)
    }
  } catch (e) {
    s.msg = `❌ 网络错误：${e.message}`
    toastErr('验证请求失败')
  } finally {
    s.verifying = false
  }
}
const dailyTasks = ref({ show: false, items: [], loading: false, busy: false, busyId: null })

async function openDailyTasks() {
  dailyTasks.value.show = true
  await loadDailyTasks()
}
async function loadDailyTasks() {
  dailyTasks.value.loading = true
  try {
    const response = await fetch('/api/daily-tasks')
    if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`)
    const items = await response.json()
    // 保留后端返回的签到状态，不覆盖成"待签到"
    dailyTasks.value.items = items.map((item) => ({
      ...item,
      ok: typeof item.checked_in === 'boolean' ? item.checked_in : null,
      message: item.status || (typeof item.checked_in === 'boolean' ? (item.checked_in ? '已签到' : '未签到') : item.message || ''),
    }))
  } catch (e) {
    toastErr('加载每日任务失败：' + e.message)
  } finally {
    dailyTasks.value.loading = false
  }
}
async function runTaskCheckin(task = null) {
  dailyTasks.value.busy = true
  dailyTasks.value.busyId = task?.account_id || null
  try {
    const url = task ? `/api/daily-tasks/checkin?account_id=${encodeURIComponent(task.account_id)}` : '/api/daily-tasks/checkin'
    const response = await fetch(url, { method: 'POST' })
    const results = await response.json()
    if (!response.ok) throw new Error(results.detail || `HTTP ${response.status}`)
    for (const result of results) {
      const row = dailyTasks.value.items.find((item) => item.account_id === result.account_id)
      if (row) Object.assign(row, { ok: result.ok, message: result.message })
    }
    const successes = results.filter((result) => result.ok).length
    const failures = results.length - successes
    if (failures) toastErr(`签到完成：${successes} 个成功，${failures} 个失败`)
    else toastOk(task ? (results[0]?.message || '签到成功') : `全部签到完成：${successes} 个账号`)
  } catch (e) {
    toastErr('签到失败：' + e.message)
  } finally {
    dailyTasks.value.busy = false
    dailyTasks.value.busyId = null
  }
}
function checkinTask(task) { return runTaskCheckin(task) }
function checkinAllTasks() { return runTaskCheckin() }

// ── Trae 浏览器登录（noVNC 沙箱） ──
const TRAE_API = '/api/trae-login'
const traeLogin = ref({ show: false, url: '', boxUp: false, pages: [], count: 0, savedFlash: false, timer: null, relayBase: '/' })
async function traeStatus() {
  try {
    const r = await fetch(`${TRAE_API}/status`)
    const j = await r.json()
    traeLogin.value.boxUp = !!(j.box && j.box.up)
    traeLogin.value.pages = (j.box && j.box.pages) || []
    if (j.relay_base) traeLogin.value.relayBase = j.relay_base
    const prev = traeLogin.value.count
    const cur = (j.accounts && j.accounts.count) || 0
    traeLogin.value.count = cur
    if (prev > 0 && cur > prev) {
      traeLogin.value.savedFlash = true
      await reload()
      toastOk('✅ 检测到新的 Trae 账号，已自动加入账号池')
    }
    if (prev === 0 && cur > 0) traeLogin.value.savedFlash = true
  } catch (e) { /* 沙箱未启动时静默 */ }
}
function helperLink(ext) {
  try {
    const configuredBase = traeLogin.value.relayBase
    const base = !configuredBase || configuredBase === '/' ? window.location.origin : configuredBase
    const url = new URL('/web/login/download', new URL(base, window.location.origin))
    if (!['http:', 'https:'].includes(url.protocol)) return ''
    url.searchParams.set('as', ext)
    return url.href
  } catch {
    return ''
  }
}
function openAuthPage() {
  try {
    const configuredBase = traeLogin.value.relayBase
    const base = !configuredBase || configuredBase === '/' ? window.location.origin : configuredBase
    const url = new URL('/web/login', new URL(base, window.location.origin))
    if (!['http:', 'https:'].includes(url.protocol)) return
    window.open(url.href, '_blank', 'noopener,noreferrer')
  } catch { return }
}
function openTraeLogin() {
  traeLogin.value.show = true
  traeLogin.value.url = '/novnc/vnc.html?autoconnect=1&resize=scale&path=websockify&reconnect=1&show_dot=1'
  fetch(`${TRAE_API}/open`, { method: 'POST' }).catch(() => {})
  if (traePollTimer !== null) { clearInterval(traePollTimer); traePollTimer = null }
  traeStatus()
  traePollTimer = setInterval(traeStatus, 4000)
  traeLogin.value.timer = traePollTimer
}
function closeTraeLogin() {
  if (traePollTimer !== null) { clearInterval(traePollTimer); traePollTimer = null }
  traeLogin.value.timer = null
  traeLogin.value.savedFlash = false
}
async function resetSandbox() {
  try {
    const r = await fetch(`${TRAE_API}/reset`, { method: 'POST' })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    toastOk('已重置到 trae2api 登录页')
  } catch (e) { toastErr('重置失败') }
}

const STATUS_MAP = {
  active: { cls: 'active-state', text: '有效' },
  expired: { cls: 'expired-state', text: '已过期' },
  error: { cls: 'error-state', text: '异常' },
  unknown: { cls: 'unknown-state', text: '未检查' },
  disabled: { cls: 'disabled-state', text: '已禁用' },
}
const statusText = (a) => (STATUS_MAP[a.status] || STATUS_MAP.unknown).text
const statusClass = (a) => (STATUS_MAP[a.status] || STATUS_MAP.unknown).cls

const PLAT_LOGO = { 'tabbit-domestic': 'dom', 'tabbit-intl': 'intl', 'loomy': 'loomy', 'trae': 'trae', 'workbuddy': 'work' }
const logoClass = (key) => PLAT_LOGO[key] || 'generic'
const logoText = (key) => (key.startsWith('tabbit') ? 'TB' : key === 'loomy' ? 'L' : key === 'trae' ? 'T' : key === 'workbuddy' ? 'W' : key.slice(0, 2).toUpperCase())
const shortId = (a) => (a.user_info && (a.user_info.id || a.user_info.user_id) ? String(a.user_info.id || a.user_info.user_id).slice(0, 8) : '')

const isLoomy = (a) => !!(a.quota_json && a.quota_json.loomy)
const isWb = (a) => !!(a.quota_json && a.quota_json.openai_compat && a.quota_json.credits != null)

const currentPlatform = computed(() => platforms.value.find((p) => p.id === dialog.value.platform_id))
const credentialPlaceholder = computed(() => {
  const ad = currentPlatform.value?.adapter
  if (ad === 'loomy') return '粘贴 Loomy Session Token…'
  if (ad === 'tabbit') return '粘贴完整 Cookie 串…'
  return '粘贴凭据（Cookie / Session / Token）…'
})
const credentialHint = computed(() => {
  const ad = currentPlatform.value?.adapter
  if (ad === 'loomy') return 'Loomy 客户端 userData/auth-session.json 里的 session 字段（有效期 14 天）。'
  if (ad === 'tabbit') return 'Tabbit 平台填浏览器完整 Cookie；凭据仅存储在本机数据库。'
  return '凭据仅存储在本机数据库，勿在公共设备使用。'
})

function wbBarPct(a) {
  const qj = a.quota_json || {}
  if (!(qj.credits_total > 0)) return null
  const used = (qj.credits_total - qj.credits) / qj.credits_total * 100
  return Math.max(0, Math.min(100, Math.round(used)))
}
function barClass(a) {
  if (isLoomy(a)) return 'na'
  if (a.status !== 'active' || a.quota_pct == null) {
    if (isWb(a) && wbBarPct(a) != null) {
      const u = wbBarPct(a)
      return u < 50 ? '' : u <= 80 ? 'mid' : 'high'
    }
    return 'na'
  }
  if (a.quota_pct < 50) return ''
  if (a.quota_pct <= 80) return 'mid'
  return 'high'
}
const barStyle = (a) => {
  if (isLoomy(a)) return {}
  if (a.quota_pct == null) {
    if (isWb(a) && wbBarPct(a) != null) return { width: wbBarPct(a) + '%' }
    return {}
  }
  return { width: Math.min(a.quota_pct, 100) + '%' }
}
function sessionDays(a) {
  const exp = (a.user_info || {}).session_expire_at
  if (!exp) return null
  const d = (new Date(exp.replace(' ', 'T')) - Date.now()) / 86400000
  return Math.ceil(d)
}
function sessionLeftClass(a) {
  const d = sessionDays(a)
  if (d === null) return ''
  if (d <= 0) return 'expired'
  if (d <= 3) return 'soon'
  return ''
}
function quotaText(a) {
  const qj = a.quota_json || {}
  if (isLoomy(a)) return (qj.available_balance != null ? qj.available_balance : '—') + ' 积分可用'
  if (isWb(a)) {
    const used = qj.credits != null && qj.credits_total > 0 ? `${qj.credits} / ${qj.credits_total} 积分` : `${qj.credits ?? '—'} 积分`
    return used
  }
  if (a.quota_pct == null) return '—'
  return a.status === 'active' ? a.quota_pct + '%' : a.quota_pct + '%（上次）'
}
function resetText(a) {
  const qj = a.quota_json || {}
  if (isLoomy(a)) return `永久 ${qj.balance ?? 0} · 每日赠送 ${qj.daily_balance ?? 0}`
  if (isWb(a)) {
    if (qj.credits_earliest_expiry) return `${qj.credits_earliest_remaining != null ? qj.credits_earliest_remaining + ' 积分' : '部分积分'} ${qj.credits_earliest_expiry.slice(0, 10)} 到期`
    if (a.status === 'active') return '积分按平台周期刷新'
    return '数据为上次检测结果'
  }
  if (qj.remaining_reset_hours != null) return `${Math.round(+qj.remaining_reset_hours)} 小时后重置额度`
  if (qj.current_cycle_end) return `额度周期至 ${qj.current_cycle_end}`
  if (a.status === 'active') return '额度周期未知'
  return '数据为上次检测结果'
}

const CRED_HELP = {
  cookie: ['浏览器登录该平台网页版,按 F12 打开开发者工具 → 应用/存储 → Cookies', '选中该站点域名,复制整条 Cookie 串(形如 a=1; b=2; session=...)', '回到本弹窗粘贴到「凭据内容」,保存后面板立即检测'],
  token: ['从平台客户端的登录态文件,或「个人设置 → 访问令牌」处复制 Token / API Key', '回到本弹窗粘贴到「凭据内容」,保存后面板立即检测'],
  json: ['复制平台导出的完整 JSON 凭据(含 token / refresh 等字段,不要漏字段)', '回到本弹窗粘贴到「凭据内容」,保存后面板立即检测'],
  browser: ['先在本机运行平台客户端完成登录,或通过面板的浏览器登录入口登录', '登录后取出会话凭据,切回 Cookie / Token 方式粘贴提交'],
}
const credHelp = computed(() => {
  const platform = platforms.value.find((item) => item.id === dialog.value.platform_id) || {}
  const allowed = modesForPlatform(platform).map((mode) => mode.id)
  const steps = []
  allowed.forEach((id) => { (CRED_HELP[id] || []).forEach((text) => steps.push(text)) })
  return { title: `${platform.name || '该平台'} · 凭据获取步骤`, steps: steps.length ? steps : ['该平台暂无预置说明,请按平台文档提交 Cookie 或 Token。'], hint: credentialHint.value }
})
async function batchCheck() {
  const targets = items.value.filter((a) => selected.value.includes(a.id))
  if (!targets.length) return
  batchBusy.value = true
  const stat = { active: 0, expired: 0, error: 0, unknown: 0 }
  const badList = []
  let failed = 0
  for (const a of targets) {
    try {
      const r = await checkAccount(a.id)
      const d = r?.data || {}
      const k = stat[d.status] != null ? d.status : 'unknown'
      stat[k] += 1
      if (k !== 'active') badList.push(`${a.name}(${STATUS_MAP[k]?.text || k}${d.status_msg ? ':' + d.status_msg : ''})`)
    } catch {
      failed += 1
      stat.error += 1
      badList.push(`${a.name}(请求失败)`)
    }
  }
  batchBusy.value = false
  const head = `批量检测 ${targets.length} 个:有效 ${stat.active} / 过期 ${stat.expired} / 异常 ${stat.error} / 未检查 ${stat.unknown}`
  if (stat.active === targets.length) toastOk(head)
  else toastErr(head + (badList.length ? `\n异常: ${badList.slice(0, 5).join('、')}${badList.length > 5 ? ` 等 ${badList.length} 个` : ''}` : ''))
  await reload()
}
async function batchDelete() {
  const targets = items.value.filter((a) => selected.value.includes(a.id))
  if (!targets.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${targets.length} 个账号吗?此操作不可恢复。`, '批量删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  batchBusy.value = true
  let done = 0
  for (const a of targets) {
    try { await deleteAccount(a.id); done += 1 } catch { /* 继续删其余的 */ }
  }
  batchBusy.value = false
  selected.value = []
  toastOk(`批量删除完成:成功 ${done}/${targets.length}`)
  await reload()
}

async function reload() {
  loading.value = true
  try {
    const params = {}
    if (platformFilter.value) params.platform_id = platformFilter.value
    if (statusFilter.value) params.status = statusFilter.value
    const base = await getAccounts(params)
    let list = base.items
    if (q.value) {
      const s = q.value.toLowerCase()
      list = list.filter((a) => (a.name + (a.platform_name || '') + (a.user_info?.secret_mobile || '') + (a.user_info?.id || '')).toLowerCase().includes(s))
    }
    items.value = list
    const last = pageCount.value
    if (page.value > last) page.value = last
    selected.value = selected.value.filter((id) => list.some((a) => a.id === id))
  } catch (e) {
    toastErr('加载账号失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function loadPlatforms() {
  try {
    const r = await getPlatforms()
    platforms.value = r.items
    if (!dialog.value.platform_id && r.items.length) dialog.value.platform_id = r.items[0].id
  } catch (e) {
    toastErr('加载平台失败：' + (e.response?.data?.detail || e.message))
  }
}

function openCreate() {
  const pid = dialog.value.platform_id || platforms.value[0]?.id
  const p = platforms.value.find(x => x.id === pid) || {}
  dialog.value = { show: true, mode: 'create', tab: 'cred', platform_id: pid, name: '', credential: '', credentialMode: (modesForPlatform(p)[0]?.id || 'cookie') }
}
function openEdit(a) {
  dialog.value = { show: true, mode: 'edit', tab: 'cred', id: a.id, platform_id: a.platform_id, name: a.name, credential: '', credentialMode: modeForAccount(a), originalType: a.credential_type }
}
async function save() {
  const d = dialog.value
  if (!d.platform_id) return toastErr('请选择平台')
  if (d.mode === 'create' && !d.name.trim()) return toastErr('请填写备注名')
  if (d.mode === 'create' && d.credentialMode === 'browser') {
    const others = credentialModesFor.value.filter(m => m.id !== 'browser').map(m => m.label).join(' / ')
    return toastErr(`请先登录后切换到 ${others} 填写凭据`)
  }
  if (d.mode === 'create' && !d.credential.trim()) return toastErr('请填写凭据')
  saving.value = true
  try {
    if (d.mode === 'create') {
      await createAccount({ platform_id: d.platform_id, name: d.name.trim(), credential: d.credential.trim(), credential_type: d.credentialMode })
      toastOk('账号已添加并完成检测')
    } else {
      const payload = { name: d.name.trim() }
      if (d.credential.trim()) {
        payload.credential = d.credential.trim()
        payload.credential_type = (d.credentialMode === 'token' && d.originalType === 'session') ? 'session' : d.credentialMode
      }
      await updateAccount(d.id, payload)
      toastOk('账号已更新')
    }
    dialog.value.show = false
    await reload()
  } catch (e) {
    toastErr('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}


function checkSummary(r) {
  const d = r?.data || r || {}
  const st = STATUS_MAP[d.status]?.text || '未知'
  const bits = []
  const qj = d.quota_json || {}
  const ui = d.user_info || {}
  if (isLoomy({ quota_json: qj })) {
    const bal = qj.available_balance != null ? qj.available_balance : (qj.balance ?? '—')
    bits.push(`积分 ${bal}${qj.daily_balance ? '（每日赠送 ' + qj.daily_balance + '）' : ''}`)
  } else if (qj.openai_compat && qj.credits != null) {
    bits.push(`积分 ${qj.credits}${qj.credits_total ? ' / ' + qj.credits_total : ''}`)
    if (qj.credits_earliest_expiry) bits.push(`${qj.credits_earliest_remaining != null ? qj.credits_earliest_remaining + ' 积分' : '部分积分'} ${qj.credits_earliest_expiry.slice(0, 10)} 到期`)
  } else if (d.quota_pct != null) {
    bits.push(`额度已用 ${d.quota_pct}%`)
  }
  if (d.member_level) bits.push(`会员 ${d.member_level}`)
  if (ui.session_expire_at) {
    const days = Math.ceil((new Date(String(ui.session_expire_at).replace(' ', 'T')) - Date.now()) / 86400000)
    bits.push(`会话剩 ${days} 天`)
  } else if (qj.current_cycle_end) {
    bits.push(`周期至 ${qj.current_cycle_end}`)
  } else if (qj.remaining_reset_hours != null) {
    bits.push(`${Math.round(+qj.remaining_reset_hours)} 小时后重置`)
  }
  const extra = d.status_msg ? `（${d.status_msg}）` : ''
  return `${st}${extra}${bits.length ? ' · ' + bits.join(' · ') : ''}`
}
async function doCheck(a) {
  busy.value = a.id
  try {
    const r = await checkAccount(a.id)
    const d = r?.data || {}
    const msg = `「${a.name}」${checkSummary(r)}`
    if (d.status === 'active') toastOk(msg)
    else toastErr(msg)
    await reload()
  } catch (e) {
    toastErr('检测失败：' + (e.response?.data?.detail || e.message))
  } finally {
    busy.value = null
  }
}

async function showModels(a) {
  models.value = { show: true, items: [], name: a.name, accountId: a.id, loading: false }
  await reloadModels()
}
async function reloadModels() {
  if (!models.value.accountId) return
  models.value.loading = true
  try {
    const r = await getAccountModels(models.value.accountId)
    models.value.items = r.items
  } catch (e) {
    toastErr('读取模型失败：' + (e.response?.data?.detail || e.message))
  } finally {
    models.value.loading = false
  }
}

async function doDelete(a) {
  try {
    await ElMessageBox.confirm(`确定删除账号「${a.name}」吗？此操作不可恢复。`, '删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deleteAccount(a.id)
    toastOk('账号已删除')
    await reload()
  } catch (e) {
    toastErr('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

function resetFilters() {
  q.value = ''
  platformFilter.value = ''
  statusFilter.value = ''
  reload()
}

onBeforeUnmount(() => {
  stopWorkbuddyPolling()
  closeTraeLogin()
  if (smsCountdownTimer !== null) clearInterval(smsCountdownTimer)
  smsCountdownTimer = null
  sms.value.tick = null
})

onMounted(() => {
  loadPlatforms()
  reload()
})
</script>
<style scoped>
.accounts-view { min-width: 0; color: var(--text); }
.accounts-view .page-head { align-items: flex-end; }
.accounts-view .head-actions { gap: 6px; }
.accounts-view .filters { align-items: center; }
.accounts-view .platform-seg { max-width: 100%; overflow-x: auto; }
.accounts-view .status-seg { flex: 0 0 auto; }
.accounts-view .search { margin-left: auto; }
.accounts-view .search .input { width: 240px; }
.accounts-view .tbl-wrap { min-height: 150px; }
.accounts-view table.tbl { min-width: 980px; }
.accounts-view .tbl th:first-child, .accounts-view .tbl td:first-child { width: 38px; }
.accounts-view .tbl th:nth-child(2) { min-width: 230px; }
.accounts-view .tbl th:nth-child(6) { min-width: 190px; }
.accounts-view .acct-copy { min-width: 0; }
.accounts-view .acct-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 210px; }
.accounts-view .quota-line { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 5px; color: var(--text-2); font-size: 11.5px; }
.accounts-view .quota-cell .bar { margin-bottom: 5px; }
.accounts-view .row-actions { display: flex; gap: 2px; white-space: nowrap; }
.accounts-view .row-actions .btn { padding-inline: 7px; }
.accounts-view .empty { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--text-2); }
.accounts-view .empty strong { color: var(--text); font-size: 13px; }
.accounts-view .empty span { color: var(--text-3); }
.accounts-view .badge .dot { width: 6px; height: 6px; box-shadow: none; }
.accounts-view .modal { width: min(560px, calc(100vw - 32px)); }
.accounts-view .modal.wide { width: min(720px, calc(100vw - 32px)); }
.accounts-view .modal .field { margin-bottom: 14px; }
.accounts-view .field .input, .accounts-view .field .select { width: 100%; }
.accounts-view textarea.input { height: auto; min-height: 112px; padding: 9px 10px; resize: vertical; }
.accounts-view .credential-tabs { width: max-content; max-width: 100%; overflow-x: auto; }
.accounts-view .browser-guide { padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); }
.accounts-view .browser-guide p, .accounts-view .task-tip { color: var(--text-2); margin-top: 5px; }
.accounts-view .hint { display: block; margin-top: 6px; color: var(--text-3); font-size: 11px; }
.accounts-view .model-list { display: flex; flex-wrap: wrap; gap: 7px; }
.accounts-view .daily-task-list { border-top: 1px solid var(--border); }
.accounts-view .daily-task-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.accounts-view .task-account { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.accounts-view .spacer { flex: 1; }
.accounts-view .oauth-steps { padding-left: 20px; color: var(--text-2); }
.accounts-view .oauth-steps li { padding: 5px 0; }
.accounts-view .oauth-steps a, .accounts-view .auth-link { color: var(--primary); overflow-wrap: anywhere; }
.accounts-view details { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; }
.accounts-view summary { cursor: pointer; color: var(--text-2); }
.accounts-view .trae-login-wrap { height: 52vh; min-height: 260px; margin-top: 10px; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.accounts-view .trae-login-frame { width: 100%; height: 100%; border: 0; }
.accounts-view .auth-link { display: block; margin-bottom: 8px; }
.accounts-view .sms-code { display: flex; gap: 8px; }
.accounts-view .sms-code .input { flex: 1; min-width: 0; }
.accounts-view .sms-msg { margin-top: 10px; color: var(--text-2); }
@media (max-width: 767px) {
  .accounts-view .head-actions { width: 100%; }
  .accounts-view .head-actions .btn { flex: 1 1 140px; }
  .accounts-view .filters { align-items: stretch; }
  .accounts-view .platform-seg, .accounts-view .status-seg { width: 100%; overflow-x: auto; }
  .accounts-view .search { width: 100%; margin-left: 0; }
  .accounts-view .search .input { width: 100%; }
  .accounts-view .daily-task-row { flex-wrap: wrap; }
}
.batch-bar{display:flex;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--border);background:rgba(127,127,127,.06);font-size:12px;color:var(--text-2)}
.batch-bar strong{color:var(--text-1)}
.cred-help{font-size:13px;line-height:1.75;color:var(--text-2)}
.cred-help strong{display:block;color:var(--text-1);margin-bottom:6px}
.cred-help ol{margin:0;padding-left:20px}
.cred-help li{margin:3px 0}
.cred-help .hint{display:block;margin-top:8px}
</style>
