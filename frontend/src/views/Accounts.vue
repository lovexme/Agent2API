<template>
  <div>
    <div class="heading">
      <div>
        <div class="eyebrow">账号池</div>
        <h1>账号管理</h1>
        <div class="sub">各平台账号、积分与可用状态一览</div>
      </div>
      <div style="display:flex; gap:8px; align-items:center">
        <button class="btn secondary" @click="openTraeLogin">🖥 Trae 浏览器登录</button>
        <button class="btn secondary" @click="openWorkbuddyLogin">🔑 WorkBuddy 授权</button>
        <button class="btn secondary" @click="openSmsLogin">📱 手机验证码添加</button>
        <button class="btn secondary" @click="openDailyTasks">📅 每日任务</button>
        <button class="btn" @click="openCreate">＋ 新增账号</button>
      </div>
    </div>

    <div class="filterbar">
      <input class="search" v-model="q" placeholder="搜索备注名 / 平台 / 用户 ID" @input="reload" />
      <select v-model="platformFilter" @change="reload">
        <option value="">全部平台</option>
        <option v-for="p in platforms" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <select v-model="statusFilter" @change="reload">
        <option value="">全部状态</option>
        <option value="active">有效</option>
        <option value="expired">已过期</option>
        <option value="error">异常</option>
        <option value="unknown">未检查</option>
        <option value="disabled">已禁用</option>
      </select>
      <button class="btn secondary sm" @click="resetFilters">重置筛选</button>
    </div>

    <div v-loading="loading" style="min-height: 200px">
      <div v-if="items.length" class="account-grid">
        <article v-for="a in items" :key="a.id" class="acct">
          <div class="acct-top">
            <div class="acct-identity">
              <span class="logo" :class="logoClass(a.platform_key)">{{ logoText(a.platform_key) }}</span>
              <div style="min-width: 0">
                <h3 class="acct-name" :title="a.name">{{ a.name }}</h3>
                <div class="account-meta">{{ a.platform_name }}<template v-if="a.user_info && a.user_info.secret_mobile"> · {{ a.user_info.secret_mobile }}</template></div>
              </div>
            </div>
            <span v-if="a.member_level" class="level">{{ a.member_level.toUpperCase() }}</span>
            <span v-if="sessionDays(a) !== null" class="session-left" :class="sessionLeftClass(a)">session 剩 {{ sessionDays(a) }} 天</span>
          </div>

          <div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center">
            <span class="state" :class="statusClass(a)">{{ statusText(a) }}</span>
            <span v-if="a.user_info" class="muted" style="font-size: 11px; color: var(--soft)">{{ shortId(a) }}</span>
          </div>

          <div class="quota">
            <div class="quota-line">
              <span>积分用量</span>
              <strong>{{ quotaText(a) }}</strong>
            </div>
            <div class="bar"><i :class="barClass(a)" :style="barStyle(a)"></i></div>
            <div class="reset">{{ resetText(a) }}</div>
          </div>

          <div class="acct-foot">
            <span class="muted">上次检查 {{ a.check_at || '从未' }}</span>
            <span class="actions">
              <button class="iconbtn" :disabled="busy===a.id" @click="doCheck(a)">↻ 检测</button>
              <button class="iconbtn" :disabled="busy===a.id" @click="showModels(a)">模型</button>
              <button class="iconbtn" @click="openEdit(a)">编辑</button>
              <button class="iconbtn" style="color: var(--red)" @click="doDelete(a)">删除</button>
            </span>
          </div>
        </article>
      </div>
      <div v-else class="empty">
        <h3>还没有账号</h3>
        <p>点击右上角「新增账号」，选择平台并粘贴 Cookie 即可接入</p>
        <button class="btn" @click="openCreate">＋ 新增账号</button>
      </div>
    </div>

    <!-- 新增/编辑 -->
    <el-dialog v-model="dialog.show" :title="dialog.mode === 'create' ? '新增账号' : '编辑账号'" width="520px">
      <div class="formgrid single">
        <div class="field">
          <label>所属平台</label>
          <select v-model="dialog.platform_id" :disabled="dialog.mode === 'edit'">
            <option v-for="p in platforms" :key="p.id" :value="p.id">{{ p.name }}（{{ p.key }}）</option>
          </select>
        </div>
        <div class="field">
          <label>备注名</label>
          <input v-model="dialog.name" placeholder="如：国内主号" />
        </div>
        <div class="field credential-field">
          <label>凭据输入方式</label>
          <div class="credential-tabs" role="tablist" aria-label="凭据输入方式">
            <button v-for="mode in credentialModes" :key="mode.id" type="button" role="tab" :aria-selected="dialog.credentialMode === mode.id" :class="{ active: dialog.credentialMode === mode.id }" @click="dialog.credentialMode = mode.id">{{ mode.label }}</button>
          </div>
          <template v-if="dialog.credentialMode === 'cookie'">
            <textarea v-model="dialog.credential" rows="6" :placeholder="credentialPlaceholder"></textarea>
            <span class="hint">{{ credentialHint }}</span>
          </template>
          <template v-else-if="dialog.credentialMode === 'token'">
            <input v-model="dialog.credential" type="password" autocomplete="off" placeholder="粘贴平台的 Access Token / API Key / Session Token" />
            <span class="hint">{{ credentialHint }}</span>
          </template>
          <template v-else-if="dialog.credentialMode === 'json'">
            <textarea v-model="dialog.credential" rows="6" placeholder='粘贴完整 JSON（如 {"cookie":"...","jwt":"..."}）'></textarea>
            <span class="hint">{{ credentialHint }}</span>
          </template>
          <div v-else class="browser-guide">
            <strong>在浏览器中登录 {{ currentPlatform?.name || '所选平台' }}</strong>
            <p>登录完成后，从平台提供的会话信息中复制 Cookie 或 Token，再切换到对应输入方式粘贴并保存。</p>
            <span class="hint">{{ credentialHint }}</span>
          </div>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn secondary" @click="dialog.show = false">取消</button>
        <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存并检测中…' : '保存并自动检测' }}</button>
      </div>
    </el-dialog>

    <!-- 模型列表 -->
    <el-dialog v-model="models.show" :title="`可用模型 — ${models.name || ''}`" width="560px">
      <div v-if="models.items.length === 0" class="empty"><h3>暂无模型数据</h3><p>点击「重新加载」获取该账号的模型列表</p></div>
      <div v-else class="model-list">
        <span v-for="m in models.items" :key="m" class="model">{{ m }}</span>
      </div>
      <div class="form-actions">
        <button class="btn secondary" @click="models.show = false">关闭</button>
        <button class="btn" :disabled="models.loading" @click="reloadModels">{{ models.loading ? '加载中…' : '重新加载' }}</button>
      </div>
    </el-dialog>

    <!-- 每日任务 -->
    <el-dialog v-model="dailyTasks.show" title="📅 每日任务" width="620px">
      <div class="daily-task-tip">Trae 签到：状态来自 Trae 账号列表；点击单个「签到」或「全部签到」执行。</div>
      <div v-if="dailyTasks.loading" class="muted" style="padding:18px 0">正在加载 Trae 账号…</div>
      <div v-else-if="!dailyTasks.items.length" class="empty daily-task-empty"><h3>暂无 Trae 账号</h3><p>Trae 网关账号列表为空</p></div>
      <div v-else class="daily-task-list">
        <div v-for="task in dailyTasks.items" :key="task.account_id" class="daily-task-row">
          <div class="daily-task-account">
            <strong>{{ task.label || task.account_id }}</strong>
            <span class="muted">{{ task.user_id || task.account_id }}</span>
          </div>
          <span class="daily-task-status" :class="task.ok === true ? 'is-ok' : task.ok === false ? 'is-fail' : ''">{{ task.message || '待签到' }}</span>
          <button class="btn secondary sm" :disabled="dailyTasks.busy" @click="checkinTask(task)">{{ dailyTasks.busyId === task.account_id ? '签到中…' : '签到' }}</button>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn secondary" :disabled="dailyTasks.loading || dailyTasks.busy" @click="loadDailyTasks">刷新状态</button>
        <button class="btn secondary" @click="dailyTasks.show = false">关闭</button>
        <button class="btn" :disabled="dailyTasks.loading || dailyTasks.busy || !dailyTasks.items.length" @click="checkinAllTasks">{{ dailyTasks.busy ? '签到中…' : '全部签到' }}</button>
      </div>
    </el-dialog>

    <!-- Trae 账号授权（OAuth 半自动，借鉴 GitHub 方式） -->
    <el-dialog v-model="traeLogin.show" title="Trae 账号授权（OAuth 半自动，跟 GitHub 一样）" width="720px" :close-on-click-modal="false" custom-class="trae-login-dialog" @closed="closeTraeLogin">
      <div class="trae-login-tip">
        <span :class="traeLogin.boxUp ? 'ok' : 'err'">{{ traeLogin.boxUp ? '● 服务就绪' : '● 沙箱未启动（不影响授权）' }}</span>
        <span class="muted">· 已保存 Trae 账号：{{ traeLogin.count }}</span>
        <span v-if="traeLogin.savedFlash" class="ok">✅ 检测到新账号，已自动刷新列表</span>
      </div>

      <ol class="oauth-steps">
        <li>
          <b>下载并运行「授权助手」</b>（在你自己的电脑上跑，负责本地回调）：
          <a :href="helperLink('bat')" download>Windows .bat</a> ·
          <a :href="helperLink('sh')" download>Mac/Linux .sh</a> ·
          <a :href="helperLink('py')" download>通用 .py</a>
        </li>
        <li>双击运行助手（会提示监听 127.0.0.1:8765，保持窗口开着）</li>
        <li>
          <b>点下方「打开授权页」</b>，在弹出的 Trae 授权页用手机号登录（滑滑块 + 填验证码）
        </li>
        <li>授权完成 → 助手自动把凭据推送到服务器 → <b>本页账号数自动 +1</b>，无需复制任何东西</li>
      </ol>

      <div class="form-actions">
        <button class="btn" @click="openAuthPage">🔗 打开授权页</button>
        <span style="flex:1"></span>
        <button class="btn secondary" @click="resetSandbox">↻ 重置沙箱</button>
        <button class="btn secondary" @click="traeLogin.show = false">关闭</button>
      </div>

      <el-collapse style="margin-top:12px">
        <el-collapse-item title="备选：沙箱实时画面（无需本机助手，直接在画布里操作）" name="sandbox">
          <div class="trae-login-wrap" style="height:52vh">
            <iframe v-if="traeLogin.show" :src="traeLogin.url" class="trae-login-frame" allow="clipboard-read; clipboard-write"></iframe>
          </div>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>

    <!-- WorkBuddy OAuth 授权 -->
    <el-dialog v-model="workbuddy.show" title="WorkBuddy 账号授权" width="620px" :close-on-click-modal="false" @closed="stopWorkbuddyPolling">
      <div class="form-field">
        <label>授权地址</label>
        <a v-if="workbuddy.url" :href="workbuddy.url" target="_blank" rel="noopener noreferrer" class="workbuddy-auth-link">{{ workbuddy.url }}</a>
        <div v-else class="muted">正在生成授权地址…</div>
        <button v-if="workbuddy.url" class="btn secondary sm" style="margin-top:8px" @click="copyWorkbuddyUrl">复制授权地址</button>
      </div>
      <p class="muted">{{ workbuddy.message || '请打开授权地址并完成登录，本页面会自动检测授权结果。' }}</p>
      <div class="form-actions"><button class="btn secondary" @click="workbuddy.show = false">关闭</button></div>
    </el-dialog>

    <!-- 手机验证码添加（发短信建号） -->
    <el-dialog v-model="sms.show" title="📱 手机验证码添加账号" width="460px" :close-on-click-modal="false">
      <div class="form-field">
        <label>平台</label>
        <select v-model="sms.platform_id">
          <option v-for="p in smsPlatforms" :key="p.id" :value="p.id">{{ p.name }}（{{ p.key }}）</option>
        </select>
      </div>
      <div class="form-field">
        <label>手机号</label>
        <input v-model="sms.phone" placeholder="输入接收验证码的手机号，如 13800138000" />
      </div>
      <div class="form-field" style="display:flex; gap:8px; align-items:center">
        <input v-model="sms.code" placeholder="短信验证码" style="flex:1" />
        <button class="btn secondary sm" :disabled="sms.sending" @click="smsSend">
          {{ sms.timer > 0 ? `${sms.timer}s 后可重发` : (sms.sending ? '发送中…' : '发送验证码') }}
        </button>
      </div>
      <p v-if="sms.msg" class="muted sms-msg">{{ sms.msg }}</p>
      <div class="form-actions">
        <button class="btn secondary" @click="sms.show = false">取消</button>
        <button class="btn" :disabled="sms.verifying" @click="smsVerify">
          {{ sms.verifying ? '验证并添加中…' : '✅ 验证并添加' }}
        </button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getAccounts, getPlatforms, createAccount, updateAccount, deleteAccount, checkAccount, refreshAccountQuota, getAccountModels } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const items = ref([])
const platforms = ref([])
const loading = ref(false)
const busy = ref(null)
const saving = ref(false)
const q = ref('')
const platformFilter = ref('')
const statusFilter = ref('')

const dialog = ref({ show: false, mode: 'create', platform_id: null, name: '', credential: '', credentialMode: 'cookie' })
const credentialModes = [
  { id: 'cookie', label: 'Cookie' },
  { id: 'token', label: 'Token / API Key' },
  { id: 'json', label: 'JSON 凭据' },
  { id: 'browser', label: '浏览器登录引导' },
]
const models = ref({ show: false, items: [], name: '', accountId: null, loading: false })
const workbuddy = ref({ show: false, state: '', url: '', message: '', timer: null })
async function openWorkbuddyLogin() {
  workbuddy.value = { show: true, state: '', url: '', message: '正在生成授权地址…', timer: null }
  try {
    const response = await fetch('/api/login/workbuddy/start', { method: 'POST' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.detail || payload.message || '授权地址生成失败')
    workbuddy.value.state = payload.state
    workbuddy.value.url = payload.url
    workbuddy.value.message = '请在授权页面完成登录，正在等待授权…'
    workbuddy.value.timer = setInterval(pollWorkbuddyStatus, 3000)
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
function stopWorkbuddyPolling() {
  if (workbuddy.value.timer) clearInterval(workbuddy.value.timer)
  workbuddy.value.timer = null
}
async function copyWorkbuddyUrl() {
  try {
    await navigator.clipboard.writeText(workbuddy.value.url)
    toastOk('授权地址已复制')
  } catch {
    toastErr('复制失败，请手动复制链接')
  }
}

// ── 手机验证码添加（发短信建号） ──
const smsPlatforms = computed(() => platforms.value.filter(p => ['loomy', 'tabbit-domestic'].includes(p.key)))
const sms = ref({ show: false, platform_id: null, phone: '', code: '', msgid: '', msg: '', timer: 0, sending: false, verifying: false, tick: null })
function openSmsLogin() {
  sms.value.show = true
  sms.value.platform_id = smsPlatforms.value[0]?.id || null
  sms.value.phone = ''
  sms.value.code = ''
  sms.value.msgid = ''
  sms.value.msg = ''
}
async function smsSend() {
  const s = sms.value
  const ph = s.phone.trim()
  if (!/^1\d{10}$/.test(ph)) return toastErr('手机号格式不对')
  if (!s.platform_id) return toastErr('请先选平台')
  const key = smsPlatforms.value.find(p => p.id === s.platform_id)?.key
  s.sending = true
  s.msg = '发送中…'
  try {
    const isTabbit = key === 'tabbit-domestic'
    const url = isTabbit ? '/api/login/tabbit/send' : `/api/login/loomy/send?phone=${encodeURIComponent(ph)}`
    const r = await fetch(url, {
      method: 'POST',
      headers: isTabbit ? { 'Content-Type': 'application/json' } : {},
      body: isTabbit ? JSON.stringify({ phone: ph }) : undefined,
    })
    const j = await r.json()
    if (j.ok) {
      if (j.msgid) s.msgid = j.msgid
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
function startSmsTimer(sec) {
  sms.value.timer = sec
  if (sms.value.tick) clearInterval(sms.value.tick)
  sms.value.tick = setInterval(() => {
    sms.value.timer -= 1
    if (sms.value.timer <= 0) clearInterval(sms.value.tick)
  }, 1000)
}
async function smsVerify() {
  const s = sms.value
  const ph = s.phone.trim()
  if (!s.msgid) return toastErr('请先发送验证码')
  if (!s.code.trim()) return toastErr('请输入验证码')
  const key = smsPlatforms.value.find(p => p.id === s.platform_id)?.key
  s.verifying = true
  s.msg = '验证中…'
  try {
    const r = await fetch(`/api/login/${key}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: ph, mcode: s.code.trim(), msgid: s.msgid }),
    })
    const j = await r.json()
    if (j.ok) {
      s.msg = `✅ 添加成功：${j.account?.name || ''}（状态 ${j.account?.status || ''}）`
      toastOk('🎉 账号已添加并入库！')
      if (s.tick) clearInterval(s.tick)
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
  const base = traeLogin.value.relayBase || '/'
  return `${base}/web/login/download?as=${ext}`
}
function openAuthPage() {
  const base = traeLogin.value.relayBase || '/'
  window.open(`${base}/web/login`, '_blank', 'noopener=false')
}
function openTraeLogin() {
  traeLogin.value.show = true
  traeLogin.value.url = '/novnc/vnc.html?autoconnect=1&resize=scale&path=websockify&reconnect=1&show_dot=1'
  fetch(`${TRAE_API}/open`, { method: 'POST' }).catch(() => {})
  traeStatus()
  if (traeLogin.value.timer) clearInterval(traeLogin.value.timer)
  traeLogin.value.timer = setInterval(traeStatus, 4000)
}
function closeTraeLogin() {
  if (traeLogin.value.timer) { clearInterval(traeLogin.value.timer); traeLogin.value.timer = null }
  traeLogin.value.savedFlash = false
}
async function resetSandbox() {
  try {
    await fetch(`${TRAE_API}/reset`, { method: 'POST' })
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

function barClass(a) {
  if (isLoomy(a)) return 'na'
  if (a.status !== 'active' || a.quota_pct == null) return 'na'
  if (a.quota_pct < 50) return ''
  if (a.quota_pct <= 80) return 'mid'
  return 'high'
}
const barStyle = (a) => (isLoomy(a) || a.status !== 'active' || a.quota_pct == null ? {} : { width: Math.min(a.quota_pct, 100) + '%' })
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
  if (a.quota_pct == null) return '—'
  return a.status === 'active' ? a.quota_pct + '%' : a.quota_pct + '%（上次）'
}
function resetText(a) {
  const qj = a.quota_json || {}
  if (isLoomy(a)) return `永久 ${qj.balance ?? 0} · 每日赠送 ${qj.daily_balance ?? 0}`
  if (qj.remaining_reset_hours != null) return `${Math.round(+qj.remaining_reset_hours)} 小时后重置额度`
  if (qj.current_cycle_end) return `额度周期至 ${qj.current_cycle_end}`
  if (a.status === 'active') return '额度周期未知'
  return '数据为上次检测结果'
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
  dialog.value = { show: true, mode: 'create', platform_id: dialog.value.platform_id || platforms.value[0]?.id, name: '', credential: '', credentialMode: 'cookie' }
}
function openEdit(a) {
  dialog.value = { show: true, mode: 'edit', id: a.id, platform_id: a.platform_id, name: a.name, credential: '', credentialMode: 'cookie' }
}
async function save() {
  const d = dialog.value
  if (!d.platform_id) return toastErr('请选择平台')
  if (d.mode === 'create' && !d.name.trim()) return toastErr('请填写备注名')
  if (d.mode === 'create' && d.credentialMode === 'browser') return toastErr('请先登录并切换到 Cookie、Token 或 JSON 凭据方式填写凭据')
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
        payload.credential_type = d.credentialMode
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

async function doCheck(a) {
  busy.value = a.id
  try {
    await checkAccount(a.id)
    toastOk(`「${a.name}」检测完成`)
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

onMounted(() => {
  loadPlatforms()
  reload()
})
</script>