// 轻量自绘 toast（与面板风格统一，不依赖 Element Plus 消息组件）
let wrap = null
function ensureWrap() {
  if (!wrap) {
    wrap = document.createElement('div')
    wrap.className = 'toast-wrap'
    document.body.appendChild(wrap)
  }
  return wrap
}
export function toast(text, type = 'ok', ms = 2600) {
  const el = document.createElement('div')
  el.className = `toast ${type}`
  el.textContent = text
  ensureWrap().appendChild(el)
  setTimeout(() => {
    el.style.transition = 'opacity .25s'
    el.style.opacity = '0'
    setTimeout(() => el.remove(), 260)
  }, ms)
}
export const toastOk = (t) => toast(t, 'ok')
export const toastErr = (t) => toast(t, 'err', 3600)
