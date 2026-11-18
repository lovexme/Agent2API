import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '总览', group: 'overview' } },
  { path: '/report', name: 'report', component: () => import('../views/Report.vue'), meta: { title: '报表', group: 'overview' } },
  { path: '/assistant', name: 'assistant', component: () => import('../views/Assistant.vue'), meta: { title: 'AI 助手', group: 'overview' } },
  { path: '/accounts', name: 'accounts', component: () => import('../views/Accounts.vue'), meta: { title: '账号管理', group: 'manage' } },
  { path: '/platforms', name: 'platforms', component: () => import('../views/Platforms.vue'), meta: { title: '平台健康', group: 'manage' } },
  { path: '/tasks', name: 'tasks', component: () => import('../views/DailyTasks.vue'), meta: { title: '每日任务', group: 'manage' } },
  { path: '/gateway', name: 'gateway', component: () => import('../views/Gateway.vue'), meta: { title: '模型路由', group: 'manage' } },
  { path: '/proxies', name: 'proxies', component: () => import('../views/Proxies.vue'), meta: { title: '网络代理', group: 'manage' } },
  { path: '/services', name: 'services', component: () => import('../views/Services.vue'), meta: { title: '工具服务', group: 'manage' } },
  { path: '/tokens', name: 'tokens', component: () => import('../views/Tokens.vue'), meta: { title: 'API 密钥', group: 'manage' } },
  { path: '/requests', name: 'requests', component: () => import('../views/Requests.vue'), meta: { title: '请求日志', group: 'manage' } },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '设置', group: 'system' } },
]

export default createRouter({ history: createWebHashHistory(), routes })