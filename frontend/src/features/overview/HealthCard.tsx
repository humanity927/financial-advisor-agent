import { useQuery } from '@tanstack/react-query';
import { Card, Descriptions, Tag, Skeleton } from 'antd';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { HealthStatus } from '../../api/types';
import StatusBadge from '../../components/StatusBadge';
import PageState from '../../components/PageState';

export default function HealthCard() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => client.get<HealthStatus>('/health', signal),
  });

  if (isLoading) {
    return (
      <Card title="系统健康">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (isError || !data?.ok) {
    return (
      <Card title="系统健康">
        <PageState state="error" error={error instanceof Error ? error.message : '健康检查失败'} onRetry={refetch} />
      </Card>
    );
  }

  const h = data.data;
  return (
    <Card title="系统健康">
      <Descriptions column={2} size="small">
        <Descriptions.Item label="状态">
          <StatusBadge status={h.status === 'healthy' ? 'healthy' : 'warning'} />
        </Descriptions.Item>
        <Descriptions.Item label="数据模式">
          <Tag color={h.force_fixture ? 'orange' : 'green'}>
            {h.force_fixture ? '演示模式' : '实时模式'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="AKShare">{h.akshare_installed ? '✅' : '❌'}</Descriptions.Item>
        <Descriptions.Item label="Fixtures">{h.fixture_available ? '✅' : '❌'}</Descriptions.Item>
        <Descriptions.Item label="缓存">{h.cache_writable ? '✅' : '❌'}</Descriptions.Item>
        <Descriptions.Item label="支持标的">{h.supported_symbol_count} 只</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}