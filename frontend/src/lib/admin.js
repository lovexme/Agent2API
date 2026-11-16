import { ref } from 'vue'

// 面板管理鉴权状态：需要登录时全屏弹登录门
export const adminState = ref({ needLogin: false, checking: true })