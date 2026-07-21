import { useLocation, useNavigate } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  LayoutDashboard,
  TrendingUp,
  Shield,
  PieChart,
  FileText,
  Bot,
  History,
} from 'lucide-react';

const { Sider } = Layout;

const NAV_ITEMS = [
  { key: '/', icon: LayoutDashboard, label: '总览' },
  { key: '/market', icon: TrendingUp, label: '行情对比' },
  { key: '/risk', icon: Shield, label: '风险实验室' },
  { key: '/portfolio', icon: PieChart, label: '配置规划' },
  { key: '/advisor', icon: Bot, label: 'Agent 咨询' },
  { key: '/report', icon: FileText, label: '正式报告' },
  { key: '/history', icon: History, label: '历史记录' },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <Sider
      width={224}
      breakpoint="lg"
      collapsedWidth={0}
      style={{
        background: '#fff',
        borderRight: '1px solid var(--color-border)',
      }}
    >
      <div
        className="shell-brand"
        style={{
          height: 54,
          display: 'flex',
          alignItems: 'center',
          padding: '0 20px',
          borderBottom: '1px solid var(--color-border)',
          fontWeight: 600,
          fontSize: 16,
          color: 'var(--color-brand)',
        }}
      >
        理财咨询工作台
      </div>
      <Menu
        mode="inline"
        selectedKeys={[location.pathname === '/' ? '/' : location.pathname]}
        items={NAV_ITEMS.map(({ key, icon: Icon, label }) => ({
          key,
          icon: <Icon size={18} />,
          label,
          onClick: () => navigate(key),
        }))}
        style={{ borderInlineEnd: 'none', marginTop: 8 }}
      />
    </Sider>
  );
}
