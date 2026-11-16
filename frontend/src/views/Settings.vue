<template>
  <div>
    <div class="heading">
      <div>
        <div class="eyebrow">实例控制</div>
        <h1>设置</h1>
        <div class="sub">密钥与运行信息</div>
      </div>
    </div>

    <div class="formgrid">
      <div class="formpanel">
        <h2>访问密钥</h2>
        <div class="formgrid single">
          <div class="field">
            <label>面板密钥（Panel Key）</label>
            <input v-model="panel_key" :placeholder="panel_key ? '已设置' : '生成中…'" />
            <span class="hint">登录面板的管理密钥（全站管理接口保护）；修改后需用新密钥登录。</span>
          </div>
          <div class="field">
            <label>网关密钥（Gateway Key）</label>
            <input v-model="gateway_key" placeholder="aam-local-key" />
            <span class="hint">调用 /v1 接口的 Bearer 密钥，修改后立即生效。</span>
          </div>
          <div class="field auto-check-field">
            <el-switch v-model="dailyCheck" />
            <div>
              <label style="display:block">每日自动检测全部账号</label>
              <span class="hint">每天 08:00 自动检测各账号状态/积分并推送汇总；仅调用免费查询接口。</span>
            </div>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>

      <div class="formpanel">
        <h2>运行信息</h2>
        <div class="formgrid single">
          <div class="field"><label>面板地址</label><input :value="origin + '/'" readonly /></div>
          <div class="field"><label>数据存储</label><input value="data/aam.db（安装目录下的 data/）" readonly /></div>
          <div class="field"><label>IPv6 访问</label><input value="已启用（后端双栈监听）" readonly /></div>
        </div>
        <div class="notice" style="margin-top: 14px">
          请求日志自动累积记录（平台 / 模型 / 成败 / 耗时），用于网关页面与总览统计。<br />
          实测账号仅存储在本机 SQLite，凭据不回传、不落日志。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { getSettings, saveSettings } from '../api'
import { toastOk, toastErr } from '../lib/toast'

const panel_key = ref('')
const gateway_key = ref('')
const saving = ref(false)
const dailyCheck = ref(true)
const origin = computed(() => window.location.origin)

async function load() {
  try {
    const s = await getSettings()
    panel_key.value = s.panel_key || ''
    gateway_key.value = s.gateway_key || 'aam-local-key'
    dailyCheck.value = (s.daily_auto_check || 'on') !== 'off'
  } catch (e) {
    toastErr('读取设置失败：' + (e.response?.data?.detail || e.message))
  }
}

async function save() {
  saving.value = true
  try {
    await saveSettings({ panel_key: panel_key.value, gateway_key: gateway_key.value, daily_auto_check: dailyCheck.value ? 'on' : 'off' })
    toastOk('设置已保存')
  } catch (e) {
    toastErr('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.auto-check-field {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}
</style>