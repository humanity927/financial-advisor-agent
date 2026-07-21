import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './app/layout/AppShell';
import OverviewPage from './features/overview/OverviewPage';
import AdvisorPage from './features/advisor/AdvisorPage';
import PageState from './components/PageState';

const MarketPage = lazy(() => import('./features/market/MarketPage'));
const PortfolioPage = lazy(() => import('./features/portfolio/PortfolioPage'));
const RiskPage = lazy(() => import('./features/risk/RiskPage'));

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
          <Route
            path="risk"
            element={
              <Suspense fallback={<PageState state="loading" />}>
                <RiskPage />
              </Suspense>
            }
          />
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
