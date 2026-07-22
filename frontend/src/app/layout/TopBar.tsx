import { useQuery } from '@tanstack/react-query';
import { Button, Spin, Tag, Tooltip } from 'antd';
import {
  Database,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { HealthStatus } from '../../api/types';

interface TopBarProps {
  collapsed: boolean;
  mobile: boolean;
  onToggleNavigation: () => void;
}

export default function TopBar({ collapsed, mobile, onToggleNavigation }: TopBarProps) {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => client.get<HealthStatus>('/health', signal),
    refetchInterval: 30_000,
  });
  const toggleLabel = collapsed ? '展开导航' : '收起导航';
  const ToggleIcon = mobile ? Menu : collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <header data-testid="system-topbar" className="shell-topbar">
      <Tooltip title={toggleLabel}>
        <Button
          type="text"
          className="shell-nav-toggle"
          icon={<ToggleIcon size={19} />}
          aria-label={toggleLabel}
          onClick={onToggleNavigation}
        />
      </Tooltip>
      <div className="topbar-mobile-brand" aria-label="当前产品">
        <span className="topbar-brand-mark" aria-hidden="true">
          <img src="/brand-mark.svg" alt="" />
        </span>
        <strong>深睡金股</strong>
      </div>
      <div className="topbar-spacer" />

      {isLoading ? (
        <Spin size="small" />
      ) : data?.ok ? (
        <div className="topbar-status-group">
          <Tag
            color={data.data.force_fixture ? 'warning' : 'success'}
            icon={<Database size={13} />}
          >
            {data.data.force_fixture ? '演示模式' : '实时优先'}
          </Tag>
          <span className="topbar-provider-status">
            <Wifi size={14} aria-hidden="true" />
            AKShare {data.data.akshare_installed ? '就绪' : '未安装'}
            <span aria-hidden="true">·</span>
            Tushare {data.data.tushare_configured ? '就绪' : '未配置'}
          </span>
        </div>
      ) : (
        <div className="topbar-status-group">
          <Tag color="error" icon={<WifiOff size={13} />}>后端未连接</Tag>
          <span className="topbar-provider-status">数据来源与 Agent 状态未知</span>
        </div>
      )}
    </header>
  );
}
