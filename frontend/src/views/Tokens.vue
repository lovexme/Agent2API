<template>
  <div class="view-wrap">
    <div class="page-head"><div><div class="page-title">API 密钥</div><div class="page-desc">客户端访问 /v1 的密钥 · 独立管理、重置与停用</div></div><div class="head-actions"><button class="btn primary" type="button" @click="openCreate">＋ 新建密钥</button></div></div>
    <div class="card master-card"><div class="card-head"><span>主密钥</span><span class="badge blue">Gateway Key</span></div><div class="card-body master-body"><div class="mono master-key">{{ masterKey }}</div><button class="btn ghost sm" type="button" @click="copy(masterKey)">复制</button></div><div class="card-body master-help">主密钥可在「设置」中修改；下方自定义密钥与其等效，可单独启停、重置。</div></div>
    <div v-loading="loading" class="card token-card"><div v-if="items.length" class="tbl-wrap"><table class="tbl"><thead><tr><th>名称</th><th>密钥</th><th>绑定平台</th><th class="r">调用</th><th>最后使用</th><th>状态</th><th class="r">操作</th></tr></thead><tbody><tr v-for="t in items" :key="t.id"><td><strong>{{ t.name }}</strong><div v-if="t.note" class="muted token-note">{{ t.note }}</div></td><td><div class="token-value"><code class="mono">{{ showFull[t.id] ? t.token : maskToken(t.token) }}</code><button class="btn ghost sm" type="button" @click="toggleShow(t)">{{ showFull[t.id] ? '隐藏' : '显示' }}</button><button class="btn ghost sm" type="button" @click="copy(t.token)">复制</button></div></td><td>{{ t.platform_key || '全部平台' }}</td><td class="r num muted">{{ t.request_count }}</td><td class="muted">{{ t.last_used_at || '未使用' }}</td><td><span class="badge" :class="t.enabled ? 'ok' : 'dim'">{{ t.enabled ? '启用' : '停用' }}</span></td><td class="r actions-cell"><button class="btn ghost sm" type="button" @click="toggleEnabled(t)">{{ t.enabled ? '停用' : '启用' }}</button><button class="btn ghost sm" type="button" @click="doReset(t)">重置</button><button class="btn danger sm" type="button" @click="doDelete(t)">删除</button></td></tr></tbody></table></div><div v-else-if="!loading" class="empty-state"><strong>还没有自定义密钥</strong><span>创建独立 API Key，便于按客户端或用途分组管理。</span><button class="btn primary sm" type="button" @click="openCreate">＋ 新建密钥</button></div></div>
    <div v-if="dialog.show || created.show" class="mask open"></div>
    <div v-if="dialog.show" class="modal open" role="dialog" aria-modal="true"><div class="modal-head">新建 API 密钥<button class="modal-close" type="button" @click="dialog.show = false">×</button></div><div class="modal-body"><div class="field"><label>名称</label><input v-model="dialog.name" class="input" placeholder="如：Cherry Studio / 手机端" /></div><div class="field"><label>绑定平台（可选）</label><select v-model="dialog.platform_key" class="select"><option value="">全部平台</option><option v-for="p in platforms" :key="p.key" :value="p.key">{{ p.name }}</option></select><span class="hint">留空 = 可调用所有平台;/v1/models 与 /chat/completions 都按此绑定过滤,调用其它平台模型会返回 403</span></div><div class="field"><label>备注（可选）</label><input v-model="dialog.note" class="input" placeholder="用途说明" /></div></div><div class="modal-foot"><button class="btn ghost" type="button" @click="dialog.show = false">取消</button><button class="btn primary" type="button" :disabled="saving" @click="save">{{ saving ? '生成中…' : '生成密钥' }}</button></div></div>
    <div v-if="created.show" class="modal open" role="dialog" aria-modal="true"><div class="modal-head">密钥已生成<button class="modal-close" type="button" @click="created.show = false">×</button></div><div class="modal-body"><p class="modal-copy">请立即复制保存，密钥可随时在列表中查看：</p><div class="keyrow"><input :value="created.value" class="input mono" readonly /><button class="btn secondary sm" type="button" @click="copy(created.value)">复制</button></div></div><div class="modal-foot"><button class="btn primary" type="button" @click="created.show = false">完成</button></div></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getTokens, createToken, updateToken, deleteToken, resetToken, getPlatforms } from '../api'
import { toastOk, toastErr } from '../lib/toast'
import { copyText } from '../lib/clipboard'

const items = ref([])
const platforms = ref([])
const masterKey = ref('')
const loading = ref(false)
const saving = ref(false)
const showFull = ref({})
const dialog = ref({ show: false, name: '', platform_key: '', note: '' })
const created = ref({ show: false, value: '' })

const maskToken = (t) => t.slice(0, 10) + '••••••••' + t.slice(-4)
function toggleShow(t) { showFull.value = { ...showFull.value, [t.id]: !showFull.value[t.id] } }

async function copy(text) {
  const ok = await copyText(text)
  if (ok) toastOk('已复制到剪贴板')
  else toastErr('复制失败,请手动选择')
}

async function load() {
  loading.value = true
  try {
    const [r, p] = await Promise.all([getTokens(), getPlatforms()])
    items.value = r.items
    masterKey.value = r.master_key
    platforms.value = p.items
  } catch (e) {
    toastErr('加载密钥失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  dialog.value = { show: true, name: '', platform_key: '', note: '' }
}
async function save() {
  if (!dialog.value.name.trim()) return toastErr('请填写密钥名称')
  saving.value = true
  try {
    const r = await createToken({ name: dialog.value.name.trim(), platform_key: dialog.value.platform_key, note: dialog.value.note.trim() })
    dialog.value.show = false
    created.value = { show: true, value: r.item.token }
    await load()
  } catch (e) {
    toastErr('创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(t) {
  try {
    await updateToken(t.id, { enabled: !t.enabled })
    toastOk(`「${t.name}」已${t.enabled ? '停用' : '启用'}`)
    await load()
  } catch (e) {
    toastErr('操作失败：' + (e.response?.data?.detail || e.message))
  }
}

async function doReset(t) {
  try {
    await ElMessageBox.confirm(`重置后「${t.name}」的旧密钥立即失效，确定继续？`, '重置密钥', { confirmButtonText: '重置', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    const r = await resetToken(t.id)
    created.value = { show: true, value: r.item.token }
    await load()
  } catch (e) {
    toastErr('重置失败：' + (e.response?.data?.detail || e.message))
  }
}

async function doDelete(t) {
  try {
    await ElMessageBox.confirm(`确定删除密钥「${t.name}」？使用它的客户端将立即无法调用。`, '删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deleteToken(t.id)
    toastOk('密钥已删除')
    await load()
  } catch (e) {
    toastErr('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>

<style scoped>
.master-card{margin-bottom:12px}.master-body{display:flex;align-items:center;gap:10px}.master-key{flex:1;min-width:0;padding:10px 12px;background:var(--surface-inset);border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.master-help{padding-top:0;color:var(--text-3);font-size:11.5px}.token-card{overflow:hidden}.token-note{font-size:11px;margin-top:2px}.token-value{display:flex;align-items:center;gap:4px;min-width:230px}.token-value code{min-width:0;overflow:hidden;text-overflow:ellipsis;color:var(--text-2)}.actions-cell{white-space:nowrap}.actions-cell .btn+.btn,.token-value .btn+.btn{margin-left:3px}.modal-close{margin-left:auto;border:0;background:transparent;color:var(--text-3);font-size:20px;line-height:1;cursor:pointer;padding:0 2px}.modal-close:hover{color:var(--text)}.modal-copy{color:var(--text-2);margin:0 0 12px}.keyrow{display:flex;align-items:center;gap:8px}.keyrow .input{flex:1;min-width:0}@media(max-width:640px){.master-body{align-items:stretch;flex-direction:column}.master-body .btn{align-self:flex-start}}</style>
