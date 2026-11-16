<template>
  <div>
    <div class="heading">
      <div>
        <div class="eyebrow">提供方注册表</div>
        <h1>平台接入</h1>
        <div class="sub">管理各平台适配器、接入地址与出口代理</div>
      </div>
      <button class="btn" @click="showForm = true">＋ 添加平台</button>
    </div>

    <div v-loading="loading" style="min-height: 160px">
      <div class="platform-manage">
        <div v-for="p in items" :key="p.id" class="platform-card">
          <div class="platform-title">
            <span class="logo" :class="logoClass(p.key)">{{ logoText(p.key) }}</span>{{ p.name }}
            <span class="state" :class="p.enabled ? 'active-state' : 'disabled-state'">{{ p.enabled ? '已启用' : '已停用' }}</span>
          </div>
          <p>适配器：<b>{{ p.adapter }}</b> · {{ p.account_count }} 个账号<template v-if="p.builtin"> · 内置</template></p>
          <code v-if="p.base_url">{{ p.base_url }}</code>
          <code v-if="p.proxy" style="color: var(--trae)">出口：{{ p.proxy }}</code>
          <div class="row" style="margin-top: 14px">
            <button class="iconbtn" :disabled="busy === p.id" @click="toggle(p)">
              {{ p.enabled ? '停用' : '启用' }}
            </button>
            <button v-if="!p.builtin" class="iconbtn" style="color: var(--red)" :disabled="busy === p.id" @click="doDelete(p)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加平台 -->
    <el-dialog v-model="showForm" title="添加自定义平台" width="540px">
      <div class="formgrid">
        <div class="field">
          <label>平台标识 key</label>
          <input v-model="form.key" placeholder="如 my-provider" />
        </div>
        <div class="field">
          <label>显示名称</label>
          <input v-model="form.name" placeholder="如 我的转发" />
        </div>
        <div class="field">
          <label>适配器类型</label>
          <select v-model="form.adapter">
            <option value="tabbit">tabbit（Tabbit 协议）</option>
            <option value="loomy">loomy（Loomy 讯飞，OpenAI 兼容）</option>
            <option value="custom">custom（OpenAI 兼容直连）</option>
            <option value="trae">trae（待接入）</option>
            <option value="workbuddy">workbuddy（待接入）</option>
          </select>
        </div>
        <div class="field">
          <label>启用</label>
          <select v-model="form.enabled">
            <option :value="1">是</option>
            <option :value="0">否</option>
          </select>
        </div>
        <div class="field">
          <label>Base URL（API 地址）</label>
          <input v-model="form.base_url" placeholder="https://api.example.com" />
        </div>
        <div class="field">
          <label>出口代理（可选）</label>
          <input v-model="form.proxy" placeholder="socks5h://127.0.0.1:1080" />
          <span class="hint">国际版服务必填出口代理，如 Tabbit 国际版走 1080</span>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn secondary" @click="showForm = false">取消</button>
        <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { getPlatforms, createPlatform, updatePlatform, deletePlatform } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const items = ref([])
const loading = ref(false)
const busy = ref(null)
const saving = ref(false)
const showForm = ref(false)
const form = ref({ key: '', name: '', adapter: 'tabbit', base_url: '', proxy: '', enabled: 1 })

const PLAT_LOGO = { 'tabbit-domestic': 'dom', 'tabbit-intl': 'intl', 'loomy': 'loomy', 'trae': 'trae', 'workbuddy': 'work' }
const logoClass = (key) => PLAT_LOGO[key] || 'generic'
const logoText = (key) => (key.startsWith('tabbit') ? 'TB' : key === 'loomy' ? 'L' : key === 'trae' ? 'T' : key === 'workbuddy' ? 'W' : key.slice(0, 2).toUpperCase())

async function load() {
  loading.value = true
  try {
    const r = await getPlatforms()
    items.value = r.items
  } catch (e) {
    toastErr('加载平台失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function save() {
  const f = form.value
  if (!f.key.trim() || !f.name.trim()) return toastErr('请填写平台标识与显示名称')
  saving.value = true
  try {
    await createPlatform({ key: f.key.trim(), name: f.name.trim(), adapter: f.adapter, base_url: f.base_url.trim(), proxy: f.proxy.trim(), enabled: !!f.enabled, meta: {} })
    toastOk('平台已添加')
    showForm.value = false
    form.value = { key: '', name: '', adapter: 'tabbit', base_url: '', proxy: '', enabled: 1 }
    await load()
  } catch (e) {
    toastErr('添加失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function toggle(p) {
  busy.value = p.id
  try {
    await updatePlatform(p.id, { enabled: !p.enabled })
    toastOk(`平台「${p.name}」已${p.enabled ? '停用' : '启用'}`)
    await load()
  } catch (e) {
    toastErr('操作失败：' + (e.response?.data?.detail || e.message))
  } finally {
    busy.value = null
  }
}

async function doDelete(p) {
  try {
    await ElMessageBox.confirm(`确认删除平台「${p.name}」？其下账号将一并删除。`, '删除确认', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  } catch { return }
  try {
    await deletePlatform(p.id)
    toastOk('平台已删除')
    await load()
  } catch (e) {
    toastErr('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>