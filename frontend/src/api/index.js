import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response && err.response.status === 401 && !String(err.config?.url || '').startsWith('/admin/')) {
      window.dispatchEvent(new CustomEvent('aam:unauthorized'))
    }
    return Promise.reject(err)
  }
)

export const getOverview = () => http.get('/overview')
export const getPlatforms = () => http.get('/platforms')
export const createPlatform = (p) => http.post('/platforms', p)
export const updatePlatform = (id, p) => http.put(`/platforms/${id}`, p)
export const deletePlatform = (id) => http.delete(`/platforms/${id}`)

export const getAccounts = (params) => http.get('/accounts', { params })
export const createAccount = (a) => http.post('/accounts', a)
export const updateAccount = (id, a) => http.put(`/accounts/${id}`, a)
export const deleteAccount = (id) => http.delete(`/accounts/${id}`)
export const checkAccount = (id) => http.post(`/accounts/${id}/check`)
export const refreshAccountQuota = (id) => http.post(`/accounts/${id}/refresh-quota`)
export const getAccountModels = (id) => http.get(`/accounts/${id}/models`)

export const getStats = (params) => http.get('/stats', { params })
export const getLogs = (params) => http.get('/logs', { params })
export const getSettings = () => http.get('/settings')
export const saveSettings = (s) => http.post('/settings', s)
export const clearLogs = () => http.post('/logs/clear')
export const runAutoCheck = () => http.post('/auto-check/run')

export const getAdminMe = () => http.get('/admin/me')
export const adminLogin = (key) => http.post('/admin/login', { key })
export const adminLogout = () => http.post('/admin/logout')

export const getTokens = () => http.get('/tokens')
export const createToken = (t) => http.post('/tokens', t)
export const updateToken = (id, t) => http.put(`/tokens/${id}`, t)
export const deleteToken = (id) => http.delete(`/tokens/${id}`)
export const resetToken = (id) => http.post(`/tokens/${id}/reset`)

// ---- 报表 ----
export const getReport = (params) => http.get('/report/summary', { params })

// ---- 工具服务 ----
export const getServices = () => http.get('/services')
export const createService = (s) => http.post('/services', s)
export const updateService = (id, s) => http.put(`/services/${id}`, s)
export const deleteService = (id) => http.delete(`/services/${id}`)
export const testService = (id) => http.post(`/services/${id}/test`)

// ---- 网络代理（平台级代理） ----
export const testPlatformProxies = (ids) => http.post('/proxies/test', { platform_ids: ids })

// ---- AI 助手 ----
export const getAssistantSessions = () => http.get('/assistant/sessions')
export const createAssistantSession = (s) => http.post('/assistant/sessions', s)
export const renameAssistantSession = (id, s) => http.put(`/assistant/sessions/${id}`, s)
export const deleteAssistantSession = (id) => http.delete(`/assistant/sessions/${id}`)
export const forkAssistantSession = (id) => http.post(`/assistant/sessions/${id}/fork`)
export const getAssistantMessages = (id) => http.get(`/assistant/sessions/${id}/messages`)
export const deleteAssistantMessage = (sid, mid) => http.delete(`/assistant/sessions/${sid}/messages/${mid}`)
export const assistantChat = (body) => http.post('/assistant/chat', body)
export const getAssistantModels = () => http.get('/assistant/models')
export const testAssistantModel = (m) => http.post('/assistant/models/test', m)

export default http