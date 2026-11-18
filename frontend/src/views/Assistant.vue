<template>
  <div class="view-wrap">
    <div class="page-head">
      <div><div class="page-title">AI 助手</div><div class="page-desc">对话式管理 · 会话保存在本地</div></div>
      <div class="head-actions">
        <select v-model="model" class="select model-pick" :disabled="!models.length || modelsLoading">
          <option value="">{{ modelsLoading ? '加载模型中...' : (models.length ? '选择模型' : '暂无可用模型') }}</option>
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
        </select>
        <button class="btn" type="button" :disabled="testing || !model" @click="runTest">{{ testing ? '测试中...' : '模型测试' }}</button>
        <button class="btn primary" type="button" :disabled="!models.length" @click="newSession">新建对话</button>
      </div>
    </div>

    <div v-if="modelsLoaded && !models.length" class="card no-model">
      <div class="empty-state">
        <strong>当前没有可用模型或账号</strong>
        <span>当前没有可用模型或账号,请先在模型管理/账号页添加。</span>
        <button class="btn sm" type="button" :disabled="modelsLoading" @click="loadModels">{{ modelsLoading ? '加载中...' : '重新加载' }}</button>
      </div>
    </div>

    <div v-else class="assistant-grid">
      <!-- 左:会话列表 -->
      <div class="card sess-pane">
        <div class="card-head">
          <span>会话</span>
          <span class="muted">{{ sessions.length }}</span>
        </div>
        <div class="sess-list">
          <div v-if="sessionsLoading && !sessions.length" class="sess-hint">加载中...</div>
          <div v-else-if="!sessions.length" class="sess-empty">
            <span class="muted">还没有会话</span>
            <button class="btn sm" type="button" :disabled="!models.length" @click="newSession">新建对话</button>
          </div>
          <div
            v-for="s in sessions"
            :key="s.id"
            class="sess-row"
            :class="{ on: s.id === currentId }"
            @click="selectSession(s.id)"
          >
            <div class="sess-main">
              <div class="sess-title" :title="s.title">{{ s.title || '未命名对话' }}</div>
              <div class="sess-meta muted mono">{{ s.msg_count || 0 }} 条 · {{ s.model || '默认模型' }}</div>
            </div>
            <div class="sess-ops" @click.stop>
              <button class="icon-btn" type="button" title="重命名" @click="openRename(s)">改</button>
              <button class="icon-btn" type="button" title="分叉" @click="forkSession(s)">叉</button>
              <button class="icon-btn danger" type="button" title="删除" @click="confirmDeleteSession(s)">删</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右:对话区 -->
      <div class="card chat-pane">
        <div class="card-head">
          <span class="chat-title">{{ currentSession ? currentSession.title : '对话' }}</span>
          <span class="muted mono">{{ model || '未选模型' }}</span>
        </div>

        <div ref="msgBox" class="msg-box">
          <div v-if="msgLoading" class="chat-hint muted">加载消息中...</div>
          <template v-else>
            <div v-if="!currentId" class="empty-state">
              <strong>未选择会话</strong>
              <span>从左侧选择一个会话,或点击「新建对话」开始。</span>
            </div>
            <div v-else-if="!messages.length" class="empty-state">
              <strong>暂无消息</strong>
              <span>在下方输入内容,按 Enter 发送。</span>
            </div>
            <div v-for="m in messages" :key="m.id" class="msg" :class="m.role === 'user' ? 'me' : 'ai'">
              <div class="msg-body">
                <div class="msg-meta">
                  <span class="badge" :class="m.role === 'user' ? 'blue' : 'dim'">{{ m.role === 'user' ? '我' : '助手' }}</span>
                  <span class="muted mono">{{ m.created_at || '' }}</span>
                </div>
                <div class="bubble">{{ m.content || '(空)' }}</div>
              </div>
              <button class="icon-btn danger msg-del" type="button" title="删除消息" @click="confirmDeleteMessage(m)">×</button>
            </div>
          </template>
        </div>

        <div class="composer">
          <textarea
            v-model="input"
            class="composer-input"
            rows="3"
            :disabled="sending || !models.length"
            placeholder="输入消息,Enter 发送,Shift + Enter 换行"
            @keydown="onKeydown"
          ></textarea>
          <div class="composer-foot">
            <span class="muted">Enter 发送 · Shift + Enter 换行</span>
            <button class="btn primary" type="button" :disabled="sending || !input.trim() || !models.length" @click="send">
              {{ sending ? '发送中...' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 重命名弹窗 -->
    <div class="mask" :class="{ open: renameOpen }" @click="renameOpen = false"></div>
    <div class="modal" :class="{ open: renameOpen }">
      <div class="modal-head">重命名会话</div>
      <div class="modal-body">
        <div class="field">
          <label>会话标题</label>
          <input v-model="renameTitle" class="input" maxlength="60" @keydown.enter.prevent="submitRename" />
          <div class="hint">最多 60 个字符</div>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn" type="button" @click="renameOpen = false">取消</button>
        <button class="btn primary" type="button" :disabled="renameSaving" @click="submitRename">{{ renameSaving ? '保存中...' : '保存' }}</button>
      </div>
    </div>

    <!-- 确认弹窗 -->
    <div class="mask" :class="{ open: !!confirmBox }" @click="confirmBox = null"></div>
    <div class="modal" :class="{ open: !!confirmBox }">
      <div class="modal-head">{{ confirmBox?.title || '确认' }}</div>
      <div class="modal-body">
        <p class="confirm-text">{{ confirmBox?.text || '' }}</p>
      </div>
      <div class="modal-foot">
        <button class="btn" type="button" @click="confirmBox = null">取消</button>
        <button class="btn danger" type="button" @click="runConfirm">{{ confirmBox?.okText || '确定' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  getAssistantSessions, createAssistantSession, renameAssistantSession, deleteAssistantSession,
  getAssistantMessages, deleteAssistantMessage, assistantChat, getAssistantModels, testAssistantModel
} from '../api'
import { toastOk, toastErr } from '../lib/toast'

const models = ref([])
const modelsLoading = ref(false)
const modelsLoaded = ref(false)
const model = ref('')

const sessions = ref([])
const sessionsLoading = ref(false)
const currentId = ref(null)
const messages = ref([])
const msgLoading = ref(false)

const input = ref('')
const sending = ref(false)
const testing = ref(false)

const msgBox = ref(null)

const renameOpen = ref(false)
const renameTitle = ref('')
const renameSaving = ref(false)
let renameTarget = null

const confirmBox = ref(null)

const currentSession = computed(() => sessions.value.find((s) => s.id === currentId.value) || null)

function errMsg(e, fallback = '请求失败') {
  return e?.response?.data?.detail || e?.message || fallback
}

function scrollBottom() {
  nextTick(() => {
    const el = msgBox.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function loadModels() {
  modelsLoading.value = true
  try {
    const r = await getAssistantModels()
    models.value = r?.items || []
    if (!models.value.length) {
      model.value = ''
      if (r?.error) toastErr('读取模型失败:' + r.error)
    } else if (!model.value || !models.value.includes(model.value)) {
      model.value = models.value[0]
    }
  } catch (e) {
    models.value = []
    model.value = ''
    toastErr('读取模型失败:' + errMsg(e))
  } finally {
    modelsLoading.value = false
    modelsLoaded.value = true
  }
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    const r = await getAssistantSessions()
    sessions.value = r?.items || []
    if (currentId.value && !sessions.value.some((s) => s.id === currentId.value)) {
      currentId.value = null
      messages.value = []
    }
  } catch (e) {
    toastErr('加载会话失败:' + errMsg(e))
  } finally {
    sessionsLoading.value = false
  }
}

async function loadMessages(id) {
  msgLoading.value = true
  try {
    const r = await getAssistantMessages(id)
    messages.value = r?.items || []
    return true
  } catch (e) {
    toastErr('加载消息失败:' + errMsg(e))
    return false
  } finally {
    msgLoading.value = false
    scrollBottom()
  }
}

async function selectSession(id) {
  if (sending.value) return
  currentId.value = id
  messages.value = []
  const s = sessions.value.find((x) => x.id === id)
  if (s?.model && models.value.includes(s.model)) model.value = s.model
  await loadMessages(id)
}

async function newSession() {
  if (!models.value.length) {
    toastErr('当前没有可用模型或账号,请先在模型管理/账号页添加')
    return
  }
  try {
    const r = await createAssistantSession({ title: '新对话', model: model.value || '' })
    const item = r?.item
    if (item) sessions.value.unshift(item)
    if (item?.id) {
      currentId.value = item.id
      messages.value = []
      toastOk('已新建对话')
    }
  } catch (e) {
    toastErr('新建会话失败:' + errMsg(e))
  }
}

function openRename(s) {
  renameTarget = s
  renameTitle.value = s.title || ''
  renameOpen.value = true
}

async function submitRename() {
  const title = renameTitle.value.trim()
  if (!title) {
    toastErr('标题不能为空')
    return
  }
  renameSaving.value = true
  try {
    const r = await renameAssistantSession(renameTarget.id, { title })
    const i = sessions.value.findIndex((s) => s.id === renameTarget.id)
    if (i >= 0) sessions.value[i] = { ...sessions.value[i], ...(r?.item || { title }) }
    renameOpen.value = false
    toastOk('已重命名')
  } catch (e) {
    toastErr('重命名失败:' + errMsg(e))
  } finally {
    renameSaving.value = false
  }
}

async function forkSession(s) {
  try {
    const r = await forkAssistantSession(s.id)
    await loadSessions()
    const item = r?.item
    if (item?.id) {
      currentId.value = item.id
      messages.value = []
      await loadMessages(item.id)
    }
    toastOk('已分叉会话')
  } catch (e) {
    toastErr('分叉失败:' + errMsg(e))
  }
}

function confirmDeleteSession(s) {
  confirmBox.value = {
    title: '删除会话',
    text: `确定删除「${s.title || '未命名对话'}」?该会话的消息将一并删除。`,
    okText: '删除',
    onOk: async () => {
      try {
        await deleteAssistantSession(s.id)
        sessions.value = sessions.value.filter((x) => x.id !== s.id)
        if (currentId.value === s.id) {
          currentId.value = null
          messages.value = []
        }
        toastOk('已删除会话')
      } catch (e) {
        toastErr('删除会话失败:' + errMsg(e))
      }
    }
  }
}

function confirmDeleteMessage(m) {
  confirmBox.value = {
    title: '删除消息',
    text: '确定删除这条消息?',
    okText: '删除',
    onOk: async () => {
      try {
        await deleteAssistantMessage(currentId.value, m.id)
        messages.value = messages.value.filter((x) => x.id !== m.id)
        const s = currentSession.value
        if (s && typeof s.msg_count === 'number' && s.msg_count > 0) s.msg_count -= 1
        toastOk('已删除消息')
      } catch (e) {
        toastErr('删除消息失败:' + errMsg(e))
      }
    }
  }
}

async function runConfirm() {
  const box = confirmBox.value
  confirmBox.value = null
  if (box?.onOk) await box.onOk()
}

async function runTest() {
  if (!model.value) {
    toastErr('请先选择模型')
    return
  }
  testing.value = true
  try {
    const r = await testAssistantModel({ model: model.value })
    if (r?.reachable) toastOk(`连通 ${r.ms}ms`)
    else toastErr('失败: ' + (r?.status || '未知错误'))
  } catch (e) {
    toastErr('测试失败:' + errMsg(e))
  } finally {
    testing.value = false
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  if (!models.value.length) {
    toastErr('当前没有可用模型或账号,请先在模型管理/账号页添加')
    return
  }
  if (!model.value) {
    toastErr('请先选择模型')
    return
  }
  sending.value = true
  try {
    let sid = currentId.value
    if (!sid) {
      const created = await createAssistantSession({ title: text.slice(0, 20), model: model.value })
      sid = created?.item?.id
      if (!sid) throw new Error('会话创建失败')
      currentId.value = sid
    }
    const history = messages.value.map((m) => ({ role: m.role, content: m.content || '' }))
    const r = await assistantChat({
      session_id: sid,
      model: model.value,
      messages: [...history, { role: 'user', content: text }],
      stream: false
    })
    input.value = ''
    const reply = r?.choices?.[0]?.message?.content || ''
    const ok = await loadMessages(sid)
    if (!ok) {
      // 落库读取失败时,本地兜底展示,避免消息看似丢失
      messages.value.push(
        { id: 'local-user-' + Date.now(), role: 'user', content: text, created_at: '' },
        { id: 'local-ai-' + Date.now(), role: 'assistant', content: reply || '(无内容)', created_at: '' }
      )
      scrollBottom()
    }
    if (!reply) toastErr('模型未返回内容')
    else toastOk(r?._ms ? `回复完成 · ${r._ms}ms` : '回复完成')
    loadSessions()
  } catch (e) {
    toastErr('发送失败:' + errMsg(e))
  } finally {
    sending.value = false
    scrollBottom()
  }
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

onMounted(async () => {
  await loadModels()
  await loadSessions()
})
</script>

<style scoped>
.model-pick{height:32px;max-width:min(280px,46vw)}

.assistant-grid{display:grid;grid-template-columns:220px 1fr;gap:12px;height:calc(100dvh - 132px);min-height:420px}
.sess-pane,.chat-pane{display:flex;flex-direction:column;min-height:0;overflow:hidden}
.sess-list{flex:1;min-height:0;overflow-y:auto;padding:6px}
.sess-hint{padding:14px;font-size:12px;color:var(--text-3)}
.sess-empty{display:flex;flex-direction:column;align-items:center;gap:8px;padding:26px 10px;font-size:12px}

.sess-row{display:flex;align-items:center;gap:6px;padding:8px 9px;border-radius:var(--radius-xs);cursor:pointer;border:1px solid transparent}
.sess-row:hover{background:var(--row-hover,var(--surface-inset))}
.sess-row.on{background:var(--primary-soft);border-color:var(--primary-tint)}
.sess-main{flex:1;min-width:0}
.sess-title{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sess-row.on .sess-title{color:var(--primary)}
.sess-meta{font-size:10.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.sess-ops{display:flex;gap:2px;opacity:0;transition:opacity .12s}
.sess-row:hover .sess-ops,.sess-row.on .sess-ops{opacity:1}
.icon-btn{width:20px;height:20px;padding:0;border:1px solid var(--border);background:var(--surface);color:var(--text-3);border-radius:6px;font-size:10.5px;line-height:1;cursor:pointer}
.icon-btn:hover{color:var(--text);border-color:var(--border-strong)}
.icon-btn.danger:hover{color:var(--danger);border-color:color-mix(in oklab,var(--danger) 40%,transparent);background:var(--danger-soft)}

.chat-pane .card-head{gap:8px}
.chat-title{font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:50%}
.msg-box{flex:1;min-height:0;overflow-y:auto;padding:14px 16px;display:flex;flex-direction:column;gap:12px}
.chat-hint{padding:18px;font-size:12px}

.msg{display:flex;align-items:flex-start;gap:6px;max-width:100%}
.msg.me{flex-direction:row-reverse}
.msg-body{max-width:78%;min-width:0}
.msg.me .msg-body{display:flex;flex-direction:column;align-items:flex-end}
.msg-meta{display:flex;align-items:center;gap:6px;font-size:10.5px;margin-bottom:4px}
.msg.me .msg-meta{flex-direction:row-reverse}
.bubble{padding:9px 12px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--surface-inset);color:var(--text);font-size:12.5px;line-height:1.6;white-space:pre-wrap;word-break:break-word}
.msg.me .bubble{background:var(--primary-soft);border-color:var(--primary-tint)}
.msg-del{flex:0 0 auto;margin-top:2px;opacity:0;transition:opacity .12s}
.msg:hover .msg-del{opacity:1}

.composer{border-top:1px solid var(--border);padding:10px 14px;display:flex;flex-direction:column;gap:8px;background:var(--surface)}
.composer-input{width:100%;min-height:64px;max-height:180px;resize:vertical;padding:9px 11px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--surface-inset);color:var(--text);font-family:var(--font-sans);font-size:12.5px;line-height:1.55;outline:none}
.composer-input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-soft)}
.composer-input::placeholder{color:var(--text-3)}
.composer-input:disabled{opacity:.6}
.composer-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:11px}

.empty-state{display:flex;flex-direction:column;align-items:center;gap:6px;padding:32px 16px;color:var(--text-3);text-align:center;font-size:12px}
.empty-state strong{color:var(--text-2);font-size:13px}
.no-model{margin-bottom:0}
.confirm-text{margin:0;font-size:12.5px;color:var(--text-2);line-height:1.6}

@media(max-width:820px){
  .assistant-grid{grid-template-columns:1fr;grid-template-rows:auto minmax(320px,1fr);height:auto}
  .sess-pane{max-height:220px}
  .chat-pane{height:calc(100dvh - 260px);min-height:360px}
  .msg-body{max-width:92%}
  .model-pick{max-width:100%;width:100%}
}
</style>
