import { useQuery } from '@tanstack/react-query';
import { Tag, Spin } from 'antd';
import { Clock, Wifi, Database } from 'lucide-react';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import SourceStamp from '../../components/SourceStamp';
import type { HealthStatus } from '../../api/types';

export default function TopBar() {
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => client.get<HealthStatus>('/health', signal),
    refetchInterval: 30_000,
  });

  return (
    <div
      data-testid="system-topbar"
      style={{
        position: 'fixed',
        top: 0,
        left: 224,
        right: 0,
        height: 54,
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        background: '#fff',
        borderBottom: '1px solid var(--color-border)',
        zIndex: 99,
        gap: 16,
      }}
    >
      {isLoading ? (
        <Spin size="small" />
      ) : data?.ok ? (
        <>
          <Tag
            color={data.data.force_fixture ? 'orange' : 'green'}
            icon={<Database size={14} />}
          >
            {data.data.force_fixture ? '演示模式' : '实时优先'}
          </Tag>
          <SourceStamp
            source={data.data.force_fixture ? 'fixture' : 'system'}
          />
          <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            <Wifi size={13} style={{ verticalAlign: 'text-bottom', marginRight: 4 }} />
            AKShare {data.data.akshare_installed ? '已就绪' : '未安装'}
          </span>
        </>
      ) : (
        <>
          <Tag color="red" icon={<Clock size={14} />}>后端未连接</Tag>
          <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            数据来源：未知
          </span>
          <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Agent 状态：未连接
          </span>
        </>
      )}
    </div>
  );
}
