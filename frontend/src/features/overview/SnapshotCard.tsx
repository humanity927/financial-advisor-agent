import { useQuery } from '@tanstack/react-query';
import { Card, Table } from 'antd';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { MarketSnapshot } from '../../api/types';
import SourceStamp from '../../components/SourceStamp';
import MetricValue from '../../components/MetricValue';
import PageState from '../../components/PageState';

const ALL_SYMBOLS = ['510300', '511010', '518880', '511880'];

export default function SnapshotCard() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: queryKeys.marketSnapshot(ALL_SYMBOLS),
    queryFn: ({ signal }) =>
      client.get<{ snapshots: MarketSnapshot[] }>('/market/snapshot?symbols=' + ALL_SYMBOLS.join(','), signal),
  });

  if (isLoading) return <PageState state="loading" />;

  if (isError || !data?.ok) {
    return <PageState state="error" error={error instanceof Error ? error.message : '行情加载失败'} onRetry={refetch} />;
  }

  const snapshots = data.data.snapshots;

  const columns = [
    { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 80 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 120 },
    { title: '最新价', dataIndex: 'latest_price', key: 'latest_price', className: 'text-right', render: (v: number) => v.toFixed(4) },
    { title: '昨日收盘', dataIndex: 'previous_close', key: 'previous_close', className: 'text-right', render: (v: number) => v.toFixed(4) },
    {
      title: '日涨跌',
      dataIndex: 'daily_change_pct',
      key: 'daily_change_pct',
      className: 'text-right',
      render: (v: number) => <MetricValue value={v} type="pct" />,
    },
    {
      title: '数据源',
      dataIndex: 'source',
      key: 'source',
      render: (source: string, record: MarketSnapshot) => (
        <span>
          <SourceStamp source={source} isFallback={record.is_fallback} />
          {record.warning && <span style={{ marginLeft: 4, fontSize: 12, color: '#faad14' }}>{record.warning}</span>}
        </span>
      ),
    },
  ];

  return (
    <Card title="市场快照">
      <Table dataSource={snapshots} columns={columns} rowKey="symbol" pagination={false} size="small" />
    </Card>
  );
}