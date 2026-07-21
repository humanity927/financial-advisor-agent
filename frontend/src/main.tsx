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
            colorPrimary: '#1A5FB4',
            borderRadius: 6,
            fontSize: 14,
            colorBorder: '#D9E0E5',
            colorBgContainer: '#FFFFFF',
            colorText: '#17212B',
            colorTextSecondary: '#667085',
            fontFamily:
              "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
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
