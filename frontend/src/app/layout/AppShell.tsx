import { Outlet } from 'react-router-dom';
import { Layout } from 'antd';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import './AppShell.css';

const { Content } = Layout;

export default function AppShell() {
  return (
    <Layout className="shell">
      <Sidebar />
      <Layout>
        <TopBar />
        <Content className="shell-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}