<template>
  <div>
    <div class="heading">
      <div>
        <div class="eyebrow">网关凭据</div>
        <h1>API 密钥</h1>
        <div class="sub">自定义调用密钥，可分发给不同客户端或用途</div>
      </div>
      <button class="btn" @click="openCreate">＋ 新建密钥</button>
    </div>

    <div class="gateway-panel">
      <h2>主密钥（Master Key）</h2>
      <div class="field">
        <div class="keyrow">
          <input :value="masterKey" readonly @click="copy(masterKey)" />
          <button class="btn secondary sm" @click="copy(masterKey)">复制</button>
        </div>
        <span class="hint">主密钥在「设置」中修改；下方自定义密钥与其等效，可单独启停、重置。</span>
      </div>
    </div>

    <div v-loading="loading" style="min-height: 200px">
      <div class="table-wrap" v-if="items.length">
        <table class="table">
          <thead>
            <tr><th>名称</th><th>密钥</th><th>绑定平台</th><th>调用</th><th>最后使用</th><th>状态</th><th style="text-align:right">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in items" :key="t.id">
              <td>
                <b>{{ t.name }}</b>
                <div v-if="t.note" class="muted" style="font-size:11px">{{ t.note }}</div>
              </td>
              <td>
                <code style="font-size:11.5px;color:#b9c9bf">{{ showFull[t.id] ? t.token : maskToken(t.token) }}</code>
                <button class="iconbtn" style="margin-left:6px" @click="toggleShow(t)">{{ showFull[t.id] ? '隐藏' : '显示' }}</button>
                <button class="iconbtn" style="margin-left:4px" @click="copy(t.token)">复制</button>
              </td>
              <td>{{ t.platform_key || '全部平台' }}</td>
              <td class="muted">{{ t.request_count }} 次</td>
              <td class="muted">{{ t.last_used_at || '未使用' }}</td>
              <td>
                <span class="state" :class="t.enabled ? 'active-state' : 'disabled-state'">{{ t.enabled ? '启用' : '停用' }}</span>
              </td>
              <td style="text-align:right;white-space:nowrap">
                <button class="iconbtn" @click="toggleEnabled(t)">{{ t.enabled ? '停用' : '启用' }}</button>
                <button class="iconbtn" style="margin-left:4px" @click="doReset(t)">重置</button>
                <button class="iconbtn" style="margin-left:4px;color:var(--red)" @click="doDelete(t)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!loading" class="empty">
        <h3>还没有自定义密钥</h3>
        <p>点击「新建密钥」生成独立 API Key，与主密钥等效，便于分组管理</p>
        <button class="btn" @click="openCreate">＋ 新建密钥</button>
      </div>
    </div>

    <el-dialog v-model="dialog.show" title="新建 API 密钥" width="500px">
      <div class="formgrid single">
        <div class="field">
          <label>名称</label>
          <input v-model="dialog.name" placeholder="如：Cherry Studio / 手机端" />
        </div>
        <div class="field">
          <label>绑定平台（可选）</label>
          <select v-model="dialog.platform_key">
            <option value="">全部平台</option>
            <option v-for="p in platforms" :key="p.key" :value="p.key">{{ p.name }}</option>
          </select>
          <span class="hint">留空表示可调用所有已接入平台的模型</span>
        </div>
        <div class="field">
          <label>备注（可选）</label>
          <input v-model="dialog.note" placeholder="用途说明" />
        </div>
      </div>
      <div class="form-actions">
        <button class="btn secondary" @click="dialog.show = false">取消</button>
        <button class="btn" :disabled="saving" @click="save">{{ saving ? '生成中…' : '生成密钥' }}</button>
      </div>
    </el-dialog>

    <el-dialog v-model="created.show" title="密钥已生成" width="560px">
      <p style="color:var(--muted);font-size:13px;margin-top:0">请立即复制保存，密钥可随时在列表中查看：</p>
      <div class="keyrow">
        <input :value="created.value" readonly />
        <button class="btn secondary sm" @click="copy(created.value)">复制</button>
      </div>
      <div class="form-actions">
        <button class="btn" @click="created.show = false">完成</button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getTokens, createToken, updateToken, deleteToken, resetToken, getPlatforms } from '../api'
import { toastOk, toastErr } from '../lib/toast'

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

function copy(text) {
  navigator.clipboard?.writeText(text).then(() => toastOk('已复制到剪贴板')).catch(() => toastErr('复制失败，请手动选择'))
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