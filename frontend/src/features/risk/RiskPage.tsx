import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Empty,
  InputNumber,
  Progress,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import {
  Activity,
  Calculator,
  Clock3,
  Database,
  ShieldCheck,
  TrendingDown,
  Waves,
} from 'lucide-react';
import { client } from '../../api/client';
import type { ProfileInput } from '../../api/types';
import ProfileForm from '../../components/ProfileForm';
import PageState from '../../components/PageState';
import SectionHeader from '../../components/SectionHeader';
import SourceStamp from '../../components/SourceStamp';
import MetricValue from '../../components/MetricValue';
import WorkspaceLayout from '../../components/WorkspaceLayout';
import { queryKeys } from '../../api/keys';
import type {
  AssetRiskData,
  AssetRiskResponse,
  PortfolioAnalysis,
  PortfolioRiskData,
  PortfolioRiskResponse,
  RiskProfileData,
} from './types';
import './RiskPage.css';
import { useWorkspace } from '../../app/WorkspaceContext';

const { Text, Title } = Typography;
const SYMBOL_OPTIONS = [
  { value: '510300', label: '510300 · 沪深300ETF' },
  { value: '511010', label: '511010 · 国债ETF' },
  { value: '518880', label: '518880 · 黄金ETF' },
  { value: '511880', label: '511880 · 货币ETF' },
];
const DEFAULT_WEIGHTS: Record<string, number> = {
  '510300': 40,
  '511010': 30,
  '518880': 20,
  '511880': 10,
};
function percent(value: number, precision = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(precision)}%`;
}

function responseError(response: { ok: boolean; error?: { message: string } } | undefined): string {
  return response?.error?.message ?? '请求未返回有效结果';
}

function formatAsOf(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) || /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  return parsed.toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' });
}

function ResultNotice({
  source,
  isFallback,
  asOf,
  warnings,
}: {
  source: string;
  isFallback: boolean;
  asOf: string;
  warnings: string[];
}) {
  const isFixture = source === 'fixture';
  const sourceMeta = (
    <div className="risk-source-meta">
      <SourceStamp source={source} isFallback={isFallback} />
      <span>
        <Clock3 size={14} />
        {source === 'system' ? '计算时间' : '数据截至'}：{formatAsOf(asOf)}
      </span>
    </div>
  );
  if (!isFixture && !isFallback && warnings.length === 0) {
    return <div className="risk-result-meta">{sourceMeta}</div>;
  }
  return (
    <Alert
      type={isFixture || isFallback ? 'warning' : 'info'}
      showIcon
      message={isFixture ? '演示数据 / 非实时数据' : isFallback ? '回退数据' : '数据提示'}
      description={warnings.length > 0 ? <ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : '当前结果可能不是最新数据。'}
      action={sourceMeta}
      className="risk-result-meta"
    />
  );
}

function ProfileResult({ profile }: { profile: RiskProfileData }) {
  const dimensions = profile.dimensions;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div className="risk-profile-summary">
        <div className="risk-profile-score">
          <span>风险评分</span>
          <strong>{profile.score}</strong>
          <small>/ 100</small>
        </div>
        <div className="risk-profile-level">
          <ShieldCheck size={28} />
          <div>
            <Title level={4}>{profile.risk_level}</Title>
            <Text type="secondary">六项画像的确定性评分结果</Text>
          </div>
        </div>
      </div>
      <Card title={<span className="risk-card-title"><Activity size={18} />六维画像</span>}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {dimensions.map((item) => (
            <div key={item.dimension}>
              <Row justify="space-between">
                <Text>{item.dimension}</Text>
                <Text strong>{item.score} / {item.max_score}</Text>
              </Row>
              <Progress percent={item.max_score ? (item.score / item.max_score) * 100 : 0} showInfo={false} />
            </div>
          ))}
        </Space>
      </Card>
      {profile.hard_limits.length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="触发的硬约束"
          description={<ul style={{ margin: 0, paddingLeft: 20 }}>{profile.hard_limits.map((item) => <li key={item}>{item}</li>)}</ul>}
        />
      )}
    </Space>
  );
}

function AssetResult({ data }: { data: AssetRiskData }) {
  const columns = [
    { title: '标的', key: 'asset', render: (_: unknown, item: AssetRiskData['assets'][number]) => <span><strong>{item.name}</strong><br /><Text type="secondary">{item.symbol} · {item.asset_class}</Text></span> },
    { title: '统计区间', key: 'period', width: 190, render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? <span>{item.metrics.start_date}<br /><Text type="secondary">至 {item.metrics.end_date}</Text></span> : '-' },
    { title: '年化收益', key: 'return', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? <MetricValue value={item.metrics.annual_return_pct} type="pct" /> : '-' },
    { title: '年化波动', key: 'volatility', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? `${item.metrics.annual_volatility_pct.toFixed(2)}%` : '-' },
    { title: '最大回撤', key: 'drawdown', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? <span className="risk-loss-value">{item.metrics.max_drawdown_pct.toFixed(2)}%</span> : '-' },
    { title: '95% VaR / CVaR', key: 'tail', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? `${item.metrics.daily_var_95_pct.toFixed(2)}% / ${item.metrics.daily_cvar_95_pct.toFixed(2)}%` : '数据不足' },
    { title: '观测数', key: 'observations', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics?.observation_count ?? '-' },
    {
      title: '状态与来源',
      key: 'source',
      width: 150,
      render: (_: unknown, item: AssetRiskData['assets'][number]) => (
        <Space direction="vertical" size={4}>
          {item.source ? <SourceStamp source={item.source} /> : <Tag color="red">数据不可用</Tag>}
          {item.error && <Text type="danger">{item.error === 'insufficient_data' ? '样本不足' : '计算失败'}</Text>}
        </Space>
      ),
    },
  ];
  return <Card title={<span className="risk-card-title"><Waves size={18} />单资产历史风险指标</span>}><Table rowKey="symbol" dataSource={data.assets} columns={columns} pagination={false} size="small" scroll={{ x: 1180 }} /></Card>;
}

function PortfolioResult({
  analysis,
  assets,
}: {
  analysis: PortfolioAnalysis;
  assets: PortfolioRiskData['assets'];
}) {
  const correlation = analysis.correlation_matrix;
  const metrics = analysis.portfolio_metrics;
  const curveOption = (points: { date: string; value: number }[], title: string, color: string): EChartsOption => ({
    title: { text: title, left: 8, textStyle: { fontSize: 14, fontWeight: 500 } },
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 44, bottom: 32 },
    xAxis: { type: 'category', data: points.map((item) => item.date), axisLabel: { hideOverlap: true, formatter: (value: string) => value.slice(5) } },
    yAxis: { type: 'value', scale: true },
    series: [{ type: 'line', data: points.map((item) => item.value), smooth: true, showSymbol: false, lineStyle: { color }, areaStyle: { color, opacity: 0.08 } }],
  });
  const netValue = analysis.net_value_curve;
  const drawdown = analysis.drawdown_curve;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div className="risk-metric-grid">
        <div><Activity size={18} /><span>年化收益</span><strong>{percent(metrics.annual_return_pct)}</strong></div>
        <div><Waves size={18} /><span>年化波动</span><strong>{metrics.annual_volatility_pct.toFixed(2)}%</strong></div>
        <div><TrendingDown size={18} /><span>最大回撤</span><strong className="risk-loss-value">{metrics.max_drawdown_pct.toFixed(2)}%</strong></div>
        <div><ShieldCheck size={18} /><span>95% VaR / CVaR</span><strong>{metrics.daily_var_95_pct.toFixed(2)}% / {metrics.daily_cvar_95_pct.toFixed(2)}%</strong></div>
      </div>
      <div className="risk-period-strip">
        <span><Clock3 size={15} />统计区间：{metrics.start_date} 至 {metrics.end_date}</span>
        <span><Database size={15} />共同有效收盘价：{metrics.observation_count} 条</span>
      </div>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}><Card>{netValue.length ? <ReactECharts option={curveOption(netValue, '组合净值', '#1A5FB4')} className="risk-chart" data-testid="risk-net-value-chart" /> : <Empty description="暂无净值曲线" />}</Card></Col>
        <Col xs={24} lg={12}><Card>{drawdown.length ? <ReactECharts option={curveOption(drawdown, '历史回撤', '#CF1322')} className="risk-chart" data-testid="risk-drawdown-chart" /> : <Empty description="暂无回撤曲线" />}</Card></Col>
      </Row>
      <Card title={<span className="risk-card-title"><Database size={18} />组合成分与数据来源</span>}>
        <Table
          size="small"
          pagination={false}
          rowKey="symbol"
          dataSource={assets}
          columns={[
            { title: '代码', dataIndex: 'symbol', key: 'symbol' },
            { title: '名称', dataIndex: 'name', key: 'name' },
            { title: '资产类别', dataIndex: 'asset_class', key: 'asset_class', render: (value: string) => <Tag>{value}</Tag> },
            { title: '权重', dataIndex: 'weight_pct', key: 'weight_pct', render: (value: number) => `${value.toFixed(2)}%` },
            { title: '来源', dataIndex: 'source', key: 'source', render: (value: string) => <SourceStamp source={value} /> },
          ]}
          scroll={{ x: 640 }}
        />
      </Card>
      <Card title={<span className="risk-card-title"><Activity size={18} />共同日期收益相关性</span>}>
        <Table
          size="small"
          pagination={false}
          rowKey="label"
          dataSource={correlation.symbols.map((label, index) => ({ label, values: correlation.values[index] ?? [] }))}
          columns={[
            { title: '标的', dataIndex: 'label', key: 'label' },
            ...correlation.symbols.map((label, index) => ({ title: label, key: label, render: (_: unknown, row: { values: Array<number | null> }) => row.values[index] == null ? '-' : row.values[index]!.toFixed(3) })),
          ]}
          scroll={{ x: 600 }}
        />
        <div className="risk-methodology">
          {Object.values(analysis.methodology).map((item) => <span key={item}>{item}</span>)}
        </div>
      </Card>
    </Space>
  );
}

function ProfilePanel() {
  const workspace = useWorkspace();
  const mutation = useMutation({
    mutationKey: queryKeys.riskProfile,
    mutationFn: (values: ProfileInput) => client.post<RiskProfileData>('/risk/profile', values),
  });
  const response = mutation.data;
  return (
    <WorkspaceLayout
      sidebar={(
        <ProfileForm
          onSubmit={(values) => { workspace.patchProfile(values); mutation.mutate(values); }}
          initialValues={workspace.profile}
          onValuesChange={workspace.patchProfile}
          loading={mutation.isPending}
          submitLabel="评估风险画像"
          submitTestId="risk-profile-submit"
        />
      )}
    >
        {mutation.isPending && <PageState state="loading" />}
        {mutation.isError && <PageState state="error" error={mutation.error instanceof Error ? mutation.error.message : '风险画像请求失败'} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
        {!mutation.isPending && !mutation.isError && !response && <PageState state="empty" emptyDescription="填写左侧画像信息后开始评估" />}
        {response && !response.ok && <PageState state="error" error={responseError(response)} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
        {response?.ok && <><ResultNotice source={response.meta.source} isFallback={response.meta.is_fallback} asOf={response.meta.as_of} warnings={response.warnings} /><ProfileResult profile={response.data} /></>}
    </WorkspaceLayout>
  );
}

function AssetPanel() {
  const workspace = useWorkspace();
  const symbolOptions = workspace.watchedSymbols.map((item) => ({
    value: item.symbol,
    label: `${item.symbol} · ${item.name}`,
  }));
  const [symbols, setSymbols] = useState(
    workspace.riskSymbol ? [workspace.riskSymbol] : workspace.selectedSymbols.slice(0, 4),
  );
  const [lookbackDays, setLookbackDays] = useState(252);
  const mutation = useMutation({
    mutationKey: queryKeys.riskAssets,
    mutationFn: (input: { symbols: string[]; lookback_days: number }) => client.post<AssetRiskData>('/risk/assets', input),
  });
  const response = mutation.data as AssetRiskResponse | undefined;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="risk-control-card" title={<span className="risk-card-title"><Waves size={18} />资产风险参数</span>}>
        <Space wrap className="risk-control-row">
          <Select aria-label="风险分析标的" mode="multiple" value={symbols} onChange={(values) => { setSymbols(values); void workspace.setRiskSymbol(values[0] ?? null); }} options={symbolOptions} maxCount={4} className="risk-symbol-select" />
          <InputNumber aria-label="资产风险回看交易日" min={60} max={1260} precision={0} value={lookbackDays} onChange={(value) => value !== null && setLookbackDays(value)} addonAfter="交易日" />
          <Button type="primary" icon={<Calculator size={15} />} onClick={() => mutation.mutate({ symbols, lookback_days: lookbackDays })} loading={mutation.isPending} disabled={symbols.length === 0} data-testid="risk-assets-submit">计算资产风险</Button>
        </Space>
        {symbols.length === 0 && <Alert type="warning" showIcon message="请至少选择一个白名单标的" style={{ marginTop: 16 }} />}
      </Card>
      {mutation.isPending && <PageState state="loading" />}
      {mutation.isError && <PageState state="error" error={mutation.error instanceof Error ? mutation.error.message : '资产风险请求失败'} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response && !response.ok && <PageState state="error" error={responseError(response)} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response?.ok && <><ResultNotice source={response.meta.source} isFallback={response.meta.is_fallback} asOf={response.meta.as_of} warnings={response.warnings} /><AssetResult data={response.data} /></>}
      {!mutation.isPending && !mutation.data && !mutation.isError && <PageState state="empty" emptyDescription="选择标的并开始计算" />}
    </Space>
  );
}

function PortfolioPanel() {
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [lookbackDays, setLookbackDays] = useState(252);
  const mutation = useMutation({
    mutationKey: queryKeys.riskPortfolio,
    mutationFn: (input: { weights_pct: Record<string, number>; lookback_days: number }) => client.post<PortfolioRiskData>('/risk/portfolio', input),
  });
  const response = mutation.data as PortfolioRiskResponse | undefined;
  const total = useMemo(() => Object.values(weights).reduce((sum, value) => sum + value, 0), [weights]);
  const analysis = response?.ok ? response.data.portfolio : null;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card className="risk-control-card" title={<span className="risk-card-title"><Calculator size={18} />固定权重每日再平衡</span>}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            {SYMBOL_OPTIONS.map((item) => <Col xs={24} sm={12} lg={6} key={item.value}><InputNumber aria-label={`${item.value} 权重`} addonBefore={item.value} addonAfter="%" min={0} max={100} precision={1} value={weights[item.value]} onChange={(value) => setWeights((old) => ({ ...old, [item.value]: value ?? 0 }))} style={{ width: '100%' }} /></Col>)}
          </Row>
          <Space wrap>
            <Tag data-testid="risk-weight-total" color={Math.abs(total - 100) < 0.000001 ? 'green' : 'red'}>权重合计：{total.toFixed(2)}%</Tag>
            <InputNumber aria-label="组合风险回看交易日" min={60} max={1260} precision={0} value={lookbackDays} onChange={(value) => value !== null && setLookbackDays(value)} addonAfter="交易日" />
            <Button type="primary" icon={<Calculator size={15} />} disabled={Math.abs(total - 100) >= 0.000001} loading={mutation.isPending} onClick={() => mutation.mutate({ weights_pct: weights, lookback_days: lookbackDays })} data-testid="risk-portfolio-submit">分析组合风险</Button>
          </Space>
          <Text type="secondary">只使用共同有效收盘价日期；指标描述历史统计，不代表未来表现。</Text>
        </Space>
      </Card>
      {mutation.isPending && <PageState state="loading" />}
      {mutation.isError && <PageState state="error" error={mutation.error instanceof Error ? mutation.error.message : '组合风险请求失败'} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response && !response.ok && <PageState state="error" error={responseError(response)} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response?.ok && !analysis && <PageState state="partial" warnings={response.warnings} />}
      {response?.ok && analysis && <><ResultNotice source={response.meta.source} isFallback={response.meta.is_fallback} asOf={response.meta.as_of} warnings={response.warnings} /><PortfolioResult analysis={analysis} assets={response.data.assets} /></>}
      {!mutation.isPending && !mutation.data && !mutation.isError && <PageState state="empty" emptyDescription="调整权重后开始组合分析" />}
    </Space>
  );
}

export default function RiskPage() {
  return (
    <div className="page-layout risk-page">
      <SectionHeader title="风险实验室" subtitle="用可复现的历史统计理解投资者画像、资产风险与组合波动" />
      <Alert
        type="info"
        showIcon
        message="教学演示边界"
        description="风险评分和指标由确定性 Python 服务计算；历史表现不代表未来收益，VaR/CVaR 不覆盖所有极端事件。"
        className="risk-boundary-alert"
      />
      <Tabs
        className="risk-tabs"
        items={[
          { key: 'profile', label: <span data-testid="risk-tab-profile">风险画像</span>, children: <ProfilePanel /> },
          { key: 'assets', label: <span data-testid="risk-tab-assets">资产风险</span>, children: <AssetPanel /> },
          { key: 'portfolio', label: <span data-testid="risk-tab-portfolio">组合风险</span>, children: <PortfolioPanel /> },
        ]}
      />
      <Divider />
      <Text type="secondary">本页面不会执行交易，也不会生成买入、卖出或收益承诺。</Text>
    </div>
  );
}
