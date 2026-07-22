import { useQuery } from '@tanstack/react-query';
import { Card, Descriptions, Tag, Skeleton, Tooltip } from 'antd';
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
      <Card title="系统健康" className="overview-health-card">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (isError || !data?.ok) {
    return (
      <Card title="系统健康" className="overview-health-card">
        <PageState state="error" error={error instanceof Error ? error.message : '健康检查失败'} onRetry={refetch} />
      </Card>
    );
  }

  const h = data.data;
  return (
    <Card title="系统健康" className="overview-health-card">
      <Descriptions column={{ xs: 1, sm: 2 }} size="small">
        <Descriptions.Item label="状态">
          <StatusBadge status={h.status === 'healthy' ? 'healthy' : 'warning'} />
        </Descriptions.Item>
        <Descriptions.Item label="数据模式">
          <Tag color={h.force_fixture ? 'orange' : 'green'}>
            {h.force_fixture ? '演示模式' : '实时模式'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="AKShare">
          <Tag color={h.akshare_installed ? 'green' : 'red'}>
            {h.akshare_installed ? '已就绪' : '未安装'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Tushare">
          <Tag color={h.tushare_configured ? 'cyan' : 'default'}>
            {h.tushare_configured ? '已配置' : '未配置'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="真实缓存">{h.cache_writable ? '可写' : '不可写'}</Descriptions.Item>
        <Descriptions.Item label="演示数据">{h.fixture_available ? '可用' : '不可用'}</Descriptions.Item>
        <Descriptions.Item
          label={(
            <Tooltip title="经过后端目录校验、可用于行情查询的 A 股指数与 ETF 元数据数量；不代表每项此刻都有可用行情。">
              <span>已校验标的</span>
            </Tooltip>
          )}
        >
          <span className="financial-number">{h.supported_symbol_count} 项</span>
        </Descriptions.Item>
        <Descriptions.Item label="来源优先级">
          {h.provider_priority.join(' → ')}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
