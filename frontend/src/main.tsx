import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import { WorkspaceProvider } from './app/WorkspaceContext';
import './styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 60_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          token: {
            colorPrimary: '#165D59',
            colorInfo: '#2F6F9F',
            colorSuccess: '#16855B',
            colorWarning: '#B7791F',
            colorError: '#B93844',
            borderRadius: 6,
            fontSize: 14,
            controlHeight: 34,
            colorBorder: '#D9E0E2',
            colorBgContainer: '#FFFFFF',
            colorBgLayout: '#F3F5F6',
            colorText: '#182226',
            colorTextSecondary: '#647176',
            fontFamily:
              "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
          },
          components: {
            Button: { fontWeight: 500 },
            Card: { headerFontSize: 14 },
            Menu: {
              itemBorderRadius: 6,
              itemHeight: 42,
              itemMarginInline: 10,
              itemSelectedBg: '#EAF4F2',
              itemSelectedColor: '#104744',
            },
            Table: {
              headerBg: '#F6F8F8',
              headerColor: '#49575C',
              rowHoverBg: '#F6FAF9',
            },
          },
        }}
      >
        <WorkspaceProvider>
          <App />
        </WorkspaceProvider>
      </ConfigProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
