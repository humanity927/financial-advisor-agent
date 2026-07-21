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
  Row,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
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
  RefreshCw,
} from 'lucide-react';
import SectionHeader from '../../components/SectionHeader';
import PageState from '../../components/PageState';
import SourceStamp from '../../components/SourceStamp';
import MetricValue from '../../components/MetricValue';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { MarketSnapshot } from '../../api/types';
import type {
  MarketCompareData,
  MarketIntervalReturn,
  MarketRange,
  MarketReturnWindow,
  MarketSourceDetail,
} from './types';
import './MarketPage.css';

const SUPPORTED_SYMBOLS = [
  { label: '沪深300ETF', value: '510300', assetClass: '股票' },
  { label: '国债ETF', value: '511010', assetClass: '债券' },
  { label: '黄金ETF', value: '518880', assetClass: '黄金' },
  { label: '货币ETF', value: '511880', assetClass: '现金' },
];

const DEFAULT_SYMBOLS = SUPPORTED_SYMBOLS.map((item) => item.value);
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
  const [range, setRange] = useState<MarketRange>('1Y');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(DEFAULT_SYMBOLS);

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
    compareQuery.data?.meta.is_fallback ||
    warnings.some((warning) => warning.includes('非实时') || warning.includes('演示数据'));

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
      <SectionHeader
        title="行情对比"
        subtitle="白名单 ETF 的归一化走势、区间收益和数据来源核验"
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
                  已选 {selectedSymbols.length} / {SUPPORTED_SYMBOLS.length} 个标的
                </Typography.Text>
              </div>
              <Space wrap>
                <Button
                  icon={<ListChecks size={14} />}
                  onClick={() => setSelectedSymbols(DEFAULT_SYMBOLS)}
                  disabled={selectedSymbols.length === DEFAULT_SYMBOLS.length}
                >
                  全选
                </Button>
                <Button
                  icon={<CircleOff size={14} />}
                  onClick={() => setSelectedSymbols([])}
                  disabled={selectedSymbols.length === 0}
                >
                  清空
                </Button>
              </Space>
            </div>

            <div className="market-filter-grid">
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
                  白名单 ETF
                </Typography.Text>
                <Checkbox.Group
                  className="market-symbol-grid"
                  value={selectedSymbols}
                  onChange={(values) => setSelectedSymbols(values.map(String))}
                >
                  {SUPPORTED_SYMBOLS.map((item) => (
                    <Checkbox className="market-symbol-option" value={item.value} key={item.value}>
                      <span className="market-symbol-copy">
                        <strong>{item.label}</strong>
                        <span>{item.value} · {item.assetClass}</span>
                      </span>
                    </Checkbox>
                  ))}
                </Checkbox.Group>
              </div>
            </div>

            {selectedSymbols.length === 0 && (
              <Alert
                type="warning"
                showIcon
                message="请至少选择一个白名单标的"
                description="当前行情接口只支持 510300、511010、518880、511880。"
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
                  type="info"
                  showIcon
                  message="数据提示"
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
