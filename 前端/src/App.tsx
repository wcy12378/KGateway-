/**
 * 前端路由入口。
 *
 * 本文件负责声明应用的页面路由和主布局挂载关系。它不负责页面数据拉取、
 * 全局状态实现或后端接口契约。
 */
import { lazy, Suspense } from 'react';
import { HashRouter, Routes, Route } from 'react-router-dom';
import { AppLayout } from '@/layouts/AppLayout';

const ChatPage = lazy(() => import('@/pages/ChatPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const BreakerPage = lazy(() => import('@/pages/BreakerPage'));
const TracesPage = lazy(() => import('@/pages/TracesPage'));
const GuidePage = lazy(() => import('@/pages/GuidePage'));
const WorkflowsPage = lazy(() => import('@/pages/WorkflowsPage'));
const PromptsPage = lazy(() => import('@/pages/PromptsPage'));
const AuditPage = lazy(() => import('@/pages/AuditPage'));

function PageFallback() {
  return <div className="page-loading">正在加载控制台...</div>;
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Suspense fallback={<PageFallback />}><ChatPage /></Suspense>} />
          <Route path="/dashboard" element={<Suspense fallback={<PageFallback />}><DashboardPage /></Suspense>} />
          <Route path="/breaker" element={<Suspense fallback={<PageFallback />}><BreakerPage /></Suspense>} />
          <Route path="/traces" element={<Suspense fallback={<PageFallback />}><TracesPage /></Suspense>} />
          <Route path="/guide" element={<Suspense fallback={<PageFallback />}><GuidePage /></Suspense>} />
          <Route path="/workflows" element={<Suspense fallback={<PageFallback />}><WorkflowsPage /></Suspense>} />
          <Route path="/prompts" element={<Suspense fallback={<PageFallback />}><PromptsPage /></Suspense>} />
          <Route path="/audit" element={<Suspense fallback={<PageFallback />}><AuditPage /></Suspense>} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
