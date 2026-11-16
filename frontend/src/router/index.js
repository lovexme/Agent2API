import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '总览', group: 'overview' } },
  { path: '/accounts', name: 'accounts', component: () => import('../views/Accounts.vue'), meta: { title: '账号管理', group: 'manage' } },
  { path: '/platforms', name: 'platforms', component: () => import('../views/Platforms.vue'), meta: { title: '平台接入', group: 'manage' } },
  { path: '/gateway', name: 'gateway', component: () => import('../views/Gateway.vue'), meta: { title: '统一网关', group: 'manage' } },
  { path: '/tokens', name: 'tokens', component: () => import('../views/Tokens.vue'), meta: { title: 'API 密钥', group: 'manage' } },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { title: '设置', group: 'system' } },
]

export default createRouter({ history: createWebHashHistory(), routes })