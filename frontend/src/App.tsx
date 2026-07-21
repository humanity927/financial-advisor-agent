import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './app/layout/AppShell';
import OverviewPage from './features/overview/OverviewPage';
import AdvisorPage from './features/advisor/AdvisorPage';
import PageState from './components/PageState';

const MarketPage = lazy(() => import('./features/market/MarketPage'));
const PortfolioPage = lazy(() => import('./features/portfolio/PortfolioPage'));

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
          <Route
            path="market"
            element={
              <Suspense fallback={<PageState state="loading" />}>
                <MarketPage />
              </Suspense>
            }
          />
          <Route path="risk" element={<LazyPage title="风险实验室" />} />
          <Route
            path="portfolio"
            element={
              <Suspense fallback={<PageState state="loading" />}>
                <PortfolioPage />
              </Suspense>
            }
          />
          <Route path="advisor" element={<AdvisorPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
