import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Empty,
  Input,
  List,
  Row,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { TableColumnsType } from 'antd';
import {
  CalendarRange,
  CircleOff,
  Clock3,
  Database,
  Layers3,
  LineChart,
  ListChecks,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import SectionHeader from '../../components/SectionHeader';
import PageState from '../../components/PageState';
import SourceStamp from '../../components/SourceStamp';
import MetricValue from '../../components/MetricValue';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { CatalogSearchData, CatalogSymbol, MarketSnapshot } from '../../api/types';
import { useWorkspace } from '../../app/WorkspaceContext';
import type {
  MarketCompareData,
  MarketIntervalReturn,
  MarketRange,
  MarketReturnWindow,
  MarketSourceDetail,
} from './types';
import './MarketPage.css';

const RANGE_OPTIONS = [
  { label: '近1月', value: '1M' },
  { label: '近3月', value: '3M' },
  { label: '近1年', value: '1Y' },
];
const RETURN_WINDOWS: MarketReturnWindow[] = ['20d', '60d', '252d'];
const CHART_COLORS = ['#2563EB', '#C58A13', '#168A5B', '#A855A0'];

interface MarketTableRow extends MarketSnapshot {
  returns?: MarketIntervalReturn['returns'];
}

function renderReturn(value: number | null | undefined) {
  if (typeof value !== 'number') {
    return <Tag>暂无</Tag>;
  }
  return <MetricValue value={value} type="pct" />;
}

function uniqueWarnings(...groups: Array<string[] | undefined>) {
  return Array.from(new Set(groups.flatMap((group) => group ?? [])));
}

function formatTimestamp(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false });
}

export default function MarketPage() {
  const {
    watchedSymbols,
    selectedSymbols,
    setSelectedSymbols,
    addSymbol,
    removeSymbol,
    watchlistLoading,
    watchlistError,
    refreshWatchlist,
  } = useWorkspace();
  const [range, setRange] = useState<MarketRange>('1Y');
  const [searchText, setSearchText] = useState('');
  const [submittedSearch, setSubmittedSearch] = useState('');
  const [messageApi, messageContext] = message.useMessage();

  const catalogQuery = useQuery({
    queryKey: ['market', 'catalog', submittedSearch],
    queryFn: ({ signal }) =>
      client.get<CatalogSearchData>(
        `/market/catalog/search?q=${encodeURIComponent(submittedSearch)}&refresh=true`,
        signal,
      ),
    enabled: submittedSearch.trim().length > 0,
    retry: false,
  });

  const handleAddSymbol = async (item: CatalogSymbol) => {
    if (watchedSymbols.length >= 8) {
      messageApi.warning('关注列表最多保留 8 个标的');
      return;
    }
    if (watchedSymbols.some((watched) => watched.symbol === item.symbol)) {
      messageApi.info(`${item.symbol} 已在关注列表`);
      return;
    }
    const result = await addSymbol(item);
    if (result.code === 'duplicate_symbol') {
      messageApi.info(`${item.symbol} 已在关注列表`);
      return;
    }
    if (!result.ok) {
      messageApi.error(result.message);
      return;
    }
    messageApi.success(result.message);
  };

  const handleRemoveSymbol = async (symbol: string) => {
    const result = await removeSymbol(symbol);
    if (result.ok) messageApi.success(result.message);
    else messageApi.error(result.message);
  };

  const handleSelection = async (symbols: string[]) => {
    const result = await setSelectedSymbols(symbols);
    if (!result.ok) messageApi.error(result.message);
  };

  const compareQuery = useQuery({
    queryKey: queryKeys.marketCompare(selectedSymbols, range),
    queryFn: ({ signal }) =>
      client.post<MarketCompareData>(
        '/market/compare',
        { symbols: selectedSymbols, range },
        signal,
      ),
    enabled: selectedSymbols.length > 0,
    retry: 1,
    staleTime: 30_000,
  });

  const comparison = compareQuery.data?.data;
  const warnings = useMemo(
    () => uniqueWarnings(compareQuery.data?.warnings, comparison?.warnings),
    [compareQuery.data?.warnings, comparison?.warnings],
  );
  const isFixture =
    compareQuery.data?.meta.source === 'fixture' ||
    warnings.some((warning) => warning.includes('非实时') || warning.includes('演示数据'));
  const isCachedFallback =
    compareQuery.data?.meta.source === 'cache' && compareQuery.data.meta.is_fallback;

  const returnBySymbol = useMemo(() => {
    return new Map(
      (comparison?.interval_returns ?? []).map((item) => [item.symbol, item.returns]),
    );
  }, [comparison?.interval_returns]);

  const tableRows = useMemo<MarketTableRow[]>(() => {
    return (comparison?.snapshots ?? []).map((snapshot) => ({
      ...snapshot,
      returns: returnBySymbol.get(snapshot.symbol),
    }));
  }, [comparison?.snapshots, returnBySymbol]);

  const chartOption = useMemo(() => {
    const series = comparison?.normalized_series ?? [];
    const dates = series[0]?.points.map((point) => point.date) ?? [];

    return {
      color: CHART_COLORS,
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: unknown) =>
          typeof value === 'number' ? value.toFixed(2) : String(value),
      },
      legend: {
        top: 0,
        type: 'scroll',
        icon: 'roundRect',
      },
      grid: {
        top: 52,
        left: 56,
        right: 28,
        bottom: 44,
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: dates,
        axisLabel: { hideOverlap: true },
        axisLine: { lineStyle: { color: '#CBD5E1' } },
      },
      yAxis: {
        type: 'value',
        name: '基准 = 100',
        scale: true,
        splitLine: { lineStyle: { color: '#E8EDF2', type: 'dashed' } },
      },
      aria: {
        enabled: true,
        decal: {
          show: true,
        },
      },
      series: series.map((item) => ({
        name: `${item.name} ${item.symbol}`,
        type: 'line',
        smooth: true,
        showSymbol: false,
        sampling: 'lttb',
        lineStyle: { width: 2.2 },
        emphasis: { focus: 'series' },
        data: item.points.map((point) => point.normalized),
      })),
    };
  }, [comparison?.normalized_series]);

  const snapshotColumns: TableColumnsType<MarketTableRow> = [
    { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 92 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 128 },
    {
      title: '资产',
      dataIndex: 'asset_class',
      key: 'asset_class',
      width: 90,
      render: (value: string) => <Tag>{value}</Tag>,
    },
    {
      title: '最新价',
      dataIndex: 'latest_price',
      key: 'latest_price',
      width: 104,
      className: 'text-right',
      render: (value: number) => value.toFixed(4),
    },
    {
      title: '日涨跌',
      dataIndex: 'daily_change_pct',
      key: 'daily_change_pct',
      width: 112,
      className: 'text-right',
      render: (value: number) => <MetricValue value={value} type="pct" />,
    },
    ...RETURN_WINDOWS.map((window) => ({
      title: window,
      key: window,
      width: 104,
      className: 'text-right',
      render: (_: unknown, row: MarketTableRow) => renderReturn(row.returns?.[window]),
    })),
    { title: '交易日', dataIndex: 'trade_date', key: 'trade_date', width: 116 },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 128,
      render: (source: string, row: MarketTableRow) => (
        <SourceStamp source={source} isFallback={row.is_fallback} />
      ),
    },
  ];

  const sourceColumns: TableColumnsType<MarketSourceDetail> = [
    { title: '代码', dataIndex: 'symbol', key: 'symbol', width: 92 },
    { title: '名称', dataIndex: 'name', key: 'name', width: 128 },
    {
      title: '数据源',
      dataIndex: 'source',
      key: 'source',
      width: 128,
      render: (source: string, row) => (
        <SourceStamp source={source} isFallback={row.is_fallback} />
      ),
    },
    {
      title: '获取时间',
      dataIndex: 'fetched_at',
      key: 'fetched_at',
      width: 190,
      render: (value: string) => formatTimestamp(value),
    },
    {
      title: '说明',
      dataIndex: 'warning',
      key: 'warning',
      render: (warning: string | null) => (
        <Typography.Text type={warning ? 'warning' : 'secondary'}>
          {warning ?? '无'}
        </Typography.Text>
      ),
    },
  ];

  const hasData = Boolean(comparison?.normalized_series.length);

  return (
    <div className="market-page">
      {messageContext}
      <SectionHeader
        title="行情对比"
        subtitle="A 股指数与 ETF 的关注管理、行情快照和多标的比较"
        actions={
          <Button
            type="primary"
            icon={<RefreshCw size={14} />}
            onClick={() => void compareQuery.refetch()}
            loading={compareQuery.isFetching}
            disabled={selectedSymbols.length === 0}
          >
            刷新数据
          </Button>
        }
      />

      <Row gutter={[24, 24]}>
        <Col span={24}>
          <Card className="market-control-card">
            <div className="market-control-heading">
              <div>
                <Typography.Title level={5}>对比范围</Typography.Title>
                <Typography.Text type="secondary">
                  已选 {selectedSymbols.length} / {watchedSymbols.length} 个关注标的
                </Typography.Text>
              </div>
              <Space wrap>
                <Button
                  icon={<ListChecks size={14} />}
                  onClick={() => void handleSelection(watchedSymbols.map((item) => item.symbol))}
                  disabled={selectedSymbols.length === watchedSymbols.length}
                >
                  全选
                </Button>
                <Button
                  icon={<CircleOff size={14} />}
                  onClick={() => void handleSelection([])}
                  disabled={selectedSymbols.length === 0}
                >
                  清空
                </Button>
              </Space>
            </div>

            {watchlistLoading && (
              <Alert type="info" showIcon message="正在恢复关注列表" />
            )}
            {watchlistError && (
              <Alert
                type="error"
                showIcon
                message="关注列表加载失败"
                description={watchlistError}
                action={(
                  <Button size="small" onClick={() => void refreshWatchlist()}>
                    重试
                  </Button>
                )}
              />
            )}

            <div className="market-filter-grid">
              <div className="market-filter-block market-search-block">
                <Typography.Text strong className="market-filter-label">
                  搜索 A 股指数或 ETF
                </Typography.Text>
                <Input.Search
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  onSearch={(value) => setSubmittedSearch(value.trim())}
                  enterButton="搜索"
                  allowClear
                  placeholder="输入代码或名称"
                  loading={catalogQuery.isFetching}
                />
                {catalogQuery.isError && (
                  <Alert
                    type="error"
                    showIcon
                    message="标的搜索失败"
                    description={catalogQuery.error instanceof Error ? catalogQuery.error.message : 'AKShare、Tushare 与本地目录均不可用'}
                  />
                )}
                {catalogQuery.isSuccess && catalogQuery.data.data.items.length === 0 && (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的指数或 ETF" />
                )}
                {catalogQuery.isSuccess && catalogQuery.data.data.items.length > 0 && (
                  <List
                    className="market-search-results"
                    size="small"
                    dataSource={catalogQuery.data.data.items}
                    renderItem={(item) => (
                      <List.Item
                        actions={[
                          <Button
                            key="add"
                            type="text"
                            icon={<Plus size={15} />}
                            aria-label={`关注 ${item.symbol}`}
                            onClick={() => void handleAddSymbol(item)}
                          />,
                        ]}
                      >
                        <List.Item.Meta
                          title={`${item.symbol} · ${item.name}`}
                          description={`${item.market} · ${item.asset_type === 'index' ? '指数' : 'ETF'} · ${item.asset_class}`}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </div>

              <div className="market-filter-block">
                <Typography.Text strong className="market-filter-label">
                  <CalendarRange size={16} />
                  观察区间
                </Typography.Text>
                <Segmented
                  block
                  options={RANGE_OPTIONS}
                  value={range}
                  onChange={(value) => setRange(value as MarketRange)}
                />
              </div>

              <div className="market-filter-block market-symbol-block">
                <Typography.Text strong className="market-filter-label">
                  <Layers3 size={16} />
                  关注列表
                </Typography.Text>
                {watchedSymbols.length === 0 ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="搜索并添加关注标的" />
                ) : (
                  <Checkbox.Group
                    className="market-symbol-grid"
                    value={selectedSymbols}
                    onChange={(values) => void handleSelection(values.map(String))}
                  >
                    {watchedSymbols.map((item) => (
                      <div className="market-symbol-option" key={item.symbol}>
                        <Checkbox value={item.symbol}>
                          <span className="market-symbol-copy">
                            <strong>{item.name}</strong>
                            <span>{item.symbol} · {item.asset_class}</span>
                          </span>
                        </Checkbox>
                        <Button
                          type="text"
                          danger
                          icon={<Trash2 size={14} />}
                          aria-label={`删除 ${item.symbol}`}
                          onClick={() => void handleRemoveSymbol(item.symbol)}
                        />
                      </div>
                    ))}
                  </Checkbox.Group>
                )}
              </div>
            </div>

            {selectedSymbols.length === 0 && (
              <Alert
                type="warning"
                showIcon
                message="请至少选择一个白名单标的"
                description="请从已校验的 A 股指数或 ETF 关注列表中选择。"
                className="market-selection-warning"
              />
            )}
          </Card>
        </Col>

        {selectedSymbols.length === 0 && (
          <Col span={24}>
            <PageState state="empty" emptyDescription="请选择标的后查看行情对比" />
          </Col>
        )}

        {selectedSymbols.length > 0 && compareQuery.isLoading && (
          <Col span={24}>
            <PageState state="loading" />
          </Col>
        )}

        {selectedSymbols.length > 0 && compareQuery.isError && (
          <Col span={24}>
            <PageState
              state="error"
              error={compareQuery.error instanceof Error ? compareQuery.error.message : '行情对比加载失败'}
              onRetry={compareQuery.refetch}
            />
          </Col>
        )}

        {selectedSymbols.length > 0 && compareQuery.isSuccess && !hasData && (
          <Col span={24}>
            <PageState
              state="empty"
              emptyDescription="共同交易日不足，暂时无法生成可比较曲线"
            />
          </Col>
        )}

        {selectedSymbols.length > 0 && compareQuery.isSuccess && comparison && hasData && (
          <>
            <Col span={24}>
              {isFixture && (
                <Alert
                  type="warning"
                  showIcon
                  message="演示数据 / 非实时行情"
                  description={warnings.length > 0 ? warnings.join('；') : '当前返回数据来自 fixture 或回退源。'}
                  className="market-data-alert"
                />
              )}
              {!isFixture && warnings.length > 0 && (
                <Alert
                  type={isCachedFallback ? 'warning' : 'info'}
                  showIcon
                  message={isCachedFallback ? '真实行情缓存 / 非实时数据' : '数据提示'}
                  description={warnings.join('；')}
                  className="market-data-alert"
                />
              )}
              <Card
                className="market-chart-card"
                title={
                  <span className="market-card-title">
                    <LineChart size={18} />
                    归一化走势
                  </span>
                }
                extra={
                  <SourceStamp
                    source={compareQuery.data.meta.source}
                    isFallback={compareQuery.data.meta.is_fallback}
                  />
                }
              >
                <div className="market-summary-strip">
                  <div>
                    <Layers3 size={17} />
                    <span>对比标的</span>
                    <strong>{comparison.symbols.length}</strong>
                  </div>
                  <div>
                    <Database size={17} />
                    <span>共同交易日</span>
                    <strong>{comparison.observation_count}</strong>
                  </div>
                  <div>
                    <Clock3 size={17} />
                    <span>数据截至</span>
                    <strong>{comparison.latest_trade_date ?? '暂无'}</strong>
                  </div>
                </div>
                <ReactECharts
                  option={chartOption}
                  notMerge
                  lazyUpdate
                  className="market-chart"
                  style={{ height: 360, width: '100%' }}
                  data-testid="market-compare-chart"
                />
              </Card>
            </Col>

            <Col span={24}>
              <Card title="区间收益与最新快照">
                <Descriptions
                  size="small"
                  column={{ xs: 1, sm: 2, lg: 4 }}
                  style={{ marginBottom: 16 }}
                >
                  <Descriptions.Item label="展示交易日">{comparison.range_days}</Descriptions.Item>
                  <Descriptions.Item label="共同起始日">{comparison.common_start_date ?? '暂无'}</Descriptions.Item>
                  <Descriptions.Item label="最新交易日">{comparison.latest_trade_date ?? '暂无'}</Descriptions.Item>
                  <Descriptions.Item label="共同交易日">{comparison.observation_count}</Descriptions.Item>
                </Descriptions>
                <Table
                  dataSource={tableRows}
                  columns={snapshotColumns}
                  rowKey="symbol"
                  pagination={false}
                  size="small"
                  scroll={{ x: 980 }}
                />
              </Card>
            </Col>

            <Col span={24}>
              <Card title="数据来源核验">
                <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
                  {comparison.method}
                </Typography.Paragraph>
                <Table
                  dataSource={comparison.source_details}
                  columns={sourceColumns}
                  rowKey="symbol"
                  pagination={false}
                  size="small"
                  scroll={{ x: 760 }}
                />
              </Card>
            </Col>
          </>
        )}
      </Row>
    </div>
  );
}
