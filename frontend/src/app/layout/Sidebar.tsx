import { useLocation, useNavigate } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  Bot,
  FileText,
  History,
  LayoutDashboard,
  PieChart,
  Shield,
  TrendingUp,
} from 'lucide-react';

const { Sider } = Layout;

const PRIMARY_NAV_ITEMS = [
  { key: '/', icon: LayoutDashboard, label: '总览' },
  { key: '/market', icon: TrendingUp, label: '行情对比' },
  { key: '/risk', icon: Shield, label: '风险实验室' },
  { key: '/portfolio', icon: PieChart, label: '配置规划' },
  { key: '/report', icon: FileText, label: '正式报告' },
];

const BOTTOM_NAV_ITEMS = [
  { key: '/advisor', icon: Bot, label: 'Agent 咨询' },
  { key: '/history', icon: History, label: '历史记录' },
];

interface SidebarProps {
  collapsed: boolean;
  mobile: boolean;
  onBreakpoint: (broken: boolean) => void;
  onNavigate: () => void;
}

export default function Sidebar({
  collapsed,
  mobile,
  onBreakpoint,
  onNavigate,
}: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const selectedKey = location.pathname === '/' ? '/' : location.pathname;

  const items = (entries: typeof PRIMARY_NAV_ITEMS) => entries.map(({ key, icon: Icon, label }) => ({
    key,
    icon: <Icon size={18} aria-hidden="true" />,
    label,
    title: label,
    onClick: () => {
      navigate(key);
      onNavigate();
    },
  }));

  return (
    <Sider
      width={228}
      collapsedWidth={mobile ? 0 : 72}
      breakpoint="lg"
      collapsed={collapsed}
      onBreakpoint={onBreakpoint}
      trigger={null}
      theme="light"
      className="shell-sidebar"
    >
      <div className="shell-sidebar-inner">
        <button
          type="button"
          className="shell-brand"
          aria-label="深睡金股总览"
          title="深睡金股"
          onClick={() => {
            navigate('/');
            onNavigate();
          }}
        >
          <span className="shell-brand-mark" aria-hidden="true">
            <img src="/brand-mark.svg" alt="" />
          </span>
          <span className="shell-brand-name">深睡金股</span>
        </button>

        <nav className="shell-primary-nav" aria-label="主要导航">
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={items(PRIMARY_NAV_ITEMS)}
          />
        </nav>

        <nav className="shell-bottom-nav" aria-label="咨询与记录">
          <span className="shell-nav-caption">咨询中心</span>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={items(BOTTOM_NAV_ITEMS)}
          />
        </nav>
      </div>
    </Sider>
  );
}
