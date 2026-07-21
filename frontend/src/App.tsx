import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './app/layout/AppShell';
import OverviewPage from './features/overview/OverviewPage';
import AdvisorPage from './features/advisor/AdvisorPage';

const LazyPage = ({ title }: { title: string }) => (
  <div style={{ padding: 48, color: '#667085', textAlign: 'center' }}>
    <h3 style={{ marginBottom: 8, color: '#17212B' }}>{title}</h3>
    <p>由功能负责人独立开发中</p>
  </div>
);

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="market" element={<LazyPage title="行情对比" />} />
          <Route path="risk" element={<LazyPage title="风险实验室" />} />
          <Route path="portfolio" element={<LazyPage title="配置规划" />} />
          <Route path="advisor" element={<AdvisorPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}