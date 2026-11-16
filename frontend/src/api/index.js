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

export const getAdminMe = () => http.get('/admin/me')
export const adminLogin = (key) => http.post('/admin/login', { key })
export const adminLogout = () => http.post('/admin/logout')

export const getTokens = () => http.get('/tokens')
export const createToken = (t) => http.post('/tokens', t)
export const updateToken = (id, t) => http.put(`/tokens/${id}`, t)
export const deleteToken = (id) => http.delete(`/tokens/${id}`)
export const resetToken = (id) => http.post(`/tokens/${id}/reset`)

export default http