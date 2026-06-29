/**
 * React 应用挂载入口。
 *
 * 本文件负责把 App 挂载到浏览器 DOM，并加载全局样式。它不负责路由定义、
 * 页面状态或后端请求。
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
