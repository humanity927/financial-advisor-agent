import { useCallback, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Layout } from 'antd';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import './AppShell.css';

const { Content } = Layout;

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);

  const handleBreakpoint = useCallback((broken: boolean) => {
    setMobile(broken);
    setCollapsed(broken);
  }, []);

  const closeMobileNavigation = useCallback(() => {
    if (mobile) setCollapsed(true);
  }, [mobile]);

  return (
    <Layout
      className={`shell ${collapsed ? 'shell-collapsed' : ''} ${mobile ? 'shell-mobile' : ''}`}
    >
      <Sidebar
        collapsed={collapsed}
        mobile={mobile}
        onBreakpoint={handleBreakpoint}
        onNavigate={closeMobileNavigation}
      />
      {mobile && !collapsed && (
        <button
          type="button"
          className="shell-backdrop"
          aria-label="关闭导航"
          onClick={() => setCollapsed(true)}
        />
      )}
      <Layout className="shell-main">
        <TopBar
          collapsed={collapsed}
          mobile={mobile}
          onToggleNavigation={() => setCollapsed((value) => !value)}
        />
        <Content className="shell-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
