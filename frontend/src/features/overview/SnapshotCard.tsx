import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Card, Space, Table, Tag, Typography } from 'antd';
import type { TableColumnsType } from 'antd';
import { Clock3, Layers3 } from 'lucide-react';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { CatalogSearchData, MarketSnapshot } from '../../api/types';
import { useWorkspace } from '../../app/WorkspaceContext';
import SourceStamp from '../../components/SourceStamp';
import MetricValue from '../../components/MetricValue';
import PageState from '../../components/PageState';
import { selectOverviewSymbols } from './snapshotSelection';

const columns: TableColumnsType<MarketSnapshot> = [
  { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 88 },
  { title: '名称', dataIndex: 'name', key: 'name', width: 132 },
  { title: '方向', dataIndex: 'asset_class', key: 'asset_class', width: 88, render: (value: string) => <Tag>{value}</Tag> },
  { title: '最新价', dataIndex: 'latest_price', key: 'latest_price', width: 106, className: 'text-right', render: (value: number) => value.toFixed(4) },
  { title: '昨日收盘', dataIndex: 'previous_close', key: 'previous_close', width: 106, className: 'text-right', render: (value: number) => value.toFixed(4) },
  {
    title: '日涨跌',
    dataIndex: 'daily_change_pct',
    key: 'daily_change_pct',
    width: 110,
    className: 'text-right',
    render: (value: number) => <MetricValue value={value} type="pct" />,
  },
  { title: '交易日', dataIndex: 'trade_date', key: 'trade_date', width: 112 },
  {
    title: '来源',
    dataIndex: 'source',
    key: 'source',
    width: 142,
    render: (source: string, record) => (
      <SourceStamp source={source} isFallback={record.is_fallback} />
    ),
  },
];

export default function SnapshotCard() {
  const { watchedSymbols, selectedSymbols, watchlistLoading } = useWorkspace();
  const catalogQuery = useQuery({
    queryKey: ['market', 'catalog', 'overview-representatives'],
    queryFn: ({ signal }) => client.get<CatalogSearchData>(
      '/market/catalog/search?q=&refresh=false&representative=true',
      signal,
    ),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const overviewItems = useMemo(
    () => selectOverviewSymbols(
      catalogQuery.data?.data.items ?? [],
      watchedSymbols,
      selectedSymbols,
    ),
    [catalogQuery.data?.data.items, selectedSymbols, watchedSymbols],
  );
  const overviewSymbols = useMemo(
    () => overviewItems.map((item) => item.symbol),
    [overviewItems],
  );
  const snapshotQuery = useQuery({
    queryKey: queryKeys.marketSnapshot(overviewSymbols),
    queryFn: ({ signal }) => client.get<{ snapshots: MarketSnapshot[] }>(
      `/market/snapshot?symbols=${overviewSymbols.join(',')}`,
      signal,
    ),
    enabled: !watchlistLoading && overviewSymbols.length > 0,
  });

  const snapshots = snapshotQuery.data?.data.snapshots ?? [];
  const source = snapshotQuery.data?.meta.source;
  const warnings = snapshotQuery.data?.warnings ?? [];
  const isFixture = source === 'fixture';
  const isCached = source === 'cache';
  const focusedCount = overviewSymbols.filter((symbol) => selectedSymbols.includes(symbol)).length;

  return (
    <Card
      title="市场快照"
      className="overview-snapshot-card"
      extra={snapshotQuery.data && (
        <Space size={8} wrap>
          <SourceStamp source={source ?? 'system'} isFallback={snapshotQuery.data.meta.is_fallback} />
          <span className="overview-as-of"><Clock3 size={13} />{snapshotQuery.data.meta.as_of}</span>
        </Space>
      )}
    >
      <div className="overview-snapshot-context">
        <span><Layers3 size={15} />{catalogQuery.data?.data.selection_note ?? '目录代表标的'}</span>
        {focusedCount > 0 && <Tag color="processing">含 {focusedCount} 个当前关注</Tag>}
      </div>

      {catalogQuery.isLoading || watchlistLoading ? (
        <PageState state="loading" />
      ) : catalogQuery.isError ? (
        <PageState
          state="error"
          error={catalogQuery.error instanceof Error ? catalogQuery.error.message : '代表标的目录加载失败'}
          onRetry={catalogQuery.refetch}
        />
      ) : snapshotQuery.isError ? (
        <PageState
          state="error"
          error={snapshotQuery.error instanceof Error ? snapshotQuery.error.message : '行情快照加载失败'}
          onRetry={snapshotQuery.refetch}
        />
      ) : overviewSymbols.length === 0 ? (
        <PageState state="empty" emptyDescription="已校验目录中暂无可展示标的" />
      ) : (
        <>
          {(isFixture || isCached || warnings.length > 0) && (
            <Alert
              className="overview-snapshot-alert"
              type={isFixture || isCached ? 'warning' : 'info'}
              showIcon
              message={isFixture ? '演示数据 / 非实时行情' : isCached ? '缓存行情' : '数据提示'}
              description={warnings.join('；') || (isCached ? '当前结果来自真实行情缓存，请以所示数据时间为准。' : '当前结果不是实时行情。')}
            />
          )}
          <Table
            dataSource={snapshots}
            columns={columns}
            rowKey="symbol"
            pagination={false}
            size="small"
            loading={snapshotQuery.isLoading}
            scroll={{ x: 884 }}
          />
          <Typography.Text type="secondary" className="overview-snapshot-note">
            默认按大盘、核心宽基、中小盘、成长、债券和黄金方向选择，并优先纳入最多两个当前对比标的。
          </Typography.Text>
        </>
      )}
    </Card>
  );
}
