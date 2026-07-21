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
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { CalculatorOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { client } from '../../api/client';
import type { ProfileInput } from '../../api/types';
import ProfileForm from '../../components/ProfileForm';
import PageState from '../../components/PageState';
import SectionHeader from '../../components/SectionHeader';
import { queryKeys } from '../../api/keys';
import type {
  AssetRiskData,
  AssetRiskResponse,
  CorrelationMatrix,
  PortfolioAnalysis,
  PortfolioRiskResponse,
  RiskDimension,
  RiskProfileData,
} from './types';

const { Text, Title } = Typography;
const SYMBOL_OPTIONS = [
  { value: '510300', label: '510300 · 沪深300ETF' },
  { value: '511010', label: '511010 · 国债ETF' },
  { value: '518880', label: '518880 · 黄金ETF' },
  { value: '511880', label: '511880 · 货币ETF' },
];
const DEFAULT_SYMBOLS = SYMBOL_OPTIONS.map((item) => item.value);
const DEFAULT_WEIGHTS: Record<string, number> = {
  '510300': 40,
  '511010': 30,
  '518880': 20,
  '511880': 10,
};
const DIMENSION_MAX: Record<string, number> = {
  投资期限: 20,
  最大可承受亏损: 30,
  投资经验: 15,
  收入稳定性: 15,
  流动性需求: 15,
  应急资金: 5,
};

function percent(value: number, precision = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(precision)}%`;
}

function profileDimensions(profile: RiskProfileData): RiskDimension[] {
  return profile.dimensions ?? Object.entries(profile.score_breakdown).map(([dimension, score]) => ({
    dimension,
    score,
    max_score: DIMENSION_MAX[dimension] ?? score,
  }));
}

function responseError(response: { ok: boolean; error?: { message: string } } | undefined): string {
  return response?.error?.message ?? '请求未返回有效结果';
}

function StateNotice({
  source,
  isFallback,
  warnings,
}: {
  source: string;
  isFallback: boolean;
  warnings: string[];
}) {
  return (
    <PageState state="success" source={source} isFallback={isFallback} warnings={warnings}>
      <></>
    </PageState>
  );
}

function ProfileResult({ profile }: { profile: RiskProfileData }) {
  const dimensions = profileDimensions(profile);
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card>
        <Row align="middle" gutter={[24, 16]}>
          <Col xs={24} md={8}>
            <Statistic title="风险评分" value={profile.score} suffix="/ 100" />
          </Col>
          <Col xs={24} md={16}>
            <Title level={4} style={{ margin: 0 }}>
              <SafetyCertificateOutlined style={{ color: '#1A5FB4', marginRight: 8 }} />
              {profile.risk_level}
            </Title>
            <Text type="secondary">评分由六项用户画像信息确定，不预测未来收益。</Text>
          </Col>
        </Row>
      </Card>
      <Card title="六维画像">
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
    { title: '年化收益', key: 'return', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? percent(item.metrics.annual_return_pct) : '-' },
    { title: '年化波动', key: 'volatility', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? percent(item.metrics.annual_volatility_pct) : '-' },
    { title: '最大回撤', key: 'drawdown', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? percent(item.metrics.max_drawdown_pct) : '-' },
    { title: '95% VaR / CVaR', key: 'tail', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics ? `${item.metrics.daily_var_95_pct.toFixed(2)}% / ${item.metrics.daily_cvar_95_pct.toFixed(2)}%` : '数据不足' },
    { title: '观测数', key: 'observations', render: (_: unknown, item: AssetRiskData['assets'][number]) => item.metrics?.observation_count ?? '-' },
  ];
  return <Card title="单资产历史风险指标"><Table rowKey="symbol" dataSource={data.assets} columns={columns} pagination={false} size="small" /></Card>;
}

function correlationParts(matrix: CorrelationMatrix): { labels: string[]; values: Array<Array<number | null>> } {
  return { labels: matrix.symbols ?? matrix.labels ?? [], values: matrix.values ?? matrix.matrix ?? [] };
}

function PortfolioResult({ analysis }: { analysis: PortfolioAnalysis }) {
  const correlation = correlationParts(analysis.correlation_matrix);
  const metrics = analysis.portfolio_metrics;
  const curveOption = (points: { date: string; value: number }[], title: string, color: string): EChartsOption => ({
    title: { text: title, left: 8, textStyle: { fontSize: 14, fontWeight: 500 } },
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 44, bottom: 32 },
    xAxis: { type: 'category', data: points.map((item) => item.date), axisLabel: { hideOverlap: true, formatter: (value: string) => value.slice(5) } },
    yAxis: { type: 'value', scale: true },
    series: [{ type: 'line', data: points.map((item) => item.value), smooth: true, showSymbol: false, lineStyle: { color }, areaStyle: { color, opacity: 0.08 } }],
  });
  const netValue = analysis.net_value_curve ?? [];
  const drawdown = analysis.drawdown_curve ?? [];
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}><Card><Statistic title="年化收益" value={metrics.annual_return_pct} precision={2} suffix="%" /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="年化波动" value={metrics.annual_volatility_pct} precision={2} suffix="%" /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="最大回撤" value={metrics.max_drawdown_pct} precision={2} suffix="%" valueStyle={{ color: '#3F8600' }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="95% VaR / CVaR" value={`${metrics.daily_var_95_pct.toFixed(2)}% / ${metrics.daily_cvar_95_pct.toFixed(2)}%`} /></Card></Col>
      </Row>
      <Card title="组合权重">
        <Space wrap>{Object.entries(analysis.weights_pct).map(([symbol, weight]) => <Tag key={symbol} color="blue">{symbol} {weight.toFixed(2)}%</Tag>)}</Space>
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}><Card>{netValue.length ? <ReactECharts option={curveOption(netValue, '组合净值', '#1A5FB4')} style={{ height: 300 }} /> : <Empty description="暂无净值曲线" />}</Card></Col>
        <Col xs={24} lg={12}><Card>{drawdown.length ? <ReactECharts option={curveOption(drawdown, '历史回撤', '#CF1322')} style={{ height: 300 }} /> : <Empty description="暂无回撤曲线" />}</Card></Col>
      </Row>
      <Card title="共同日期收益相关性">
        <Table
          size="small"
          pagination={false}
          rowKey="label"
          dataSource={correlation.labels.map((label, index) => ({ label, values: correlation.values[index] ?? [] }))}
          columns={[
            { title: '标的', dataIndex: 'label', key: 'label' },
            ...correlation.labels.map((label, index) => ({ title: label, key: label, render: (_: unknown, row: { values: Array<number | null> }) => row.values[index] == null ? '-' : row.values[index]!.toFixed(3) })),
          ]}
        />
      </Card>
    </Space>
  );
}

function ProfilePanel() {
  const mutation = useMutation({
    mutationKey: queryKeys.riskProfile,
    mutationFn: (values: ProfileInput) => client.post<RiskProfileData>('/risk/profile', values),
  });
  const response = mutation.data;
  return (
    <Row gutter={[24, 24]}>
      <Col xs={24} lg={8}><ProfileForm onSubmit={(values) => mutation.mutate(values)} loading={mutation.isPending} /></Col>
      <Col xs={24} lg={16}>
        {mutation.isPending && <PageState state="loading" />}
        {mutation.isError && <PageState state="error" error={mutation.error instanceof Error ? mutation.error.message : '风险画像请求失败'} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
        {!mutation.isPending && !mutation.isError && !response && <PageState state="empty" emptyDescription="填写左侧画像信息后开始评估" />}
        {response && !response.ok && <PageState state="error" error={responseError(response)} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
        {response?.ok && <><StateNotice source={response.meta.source} isFallback={response.meta.is_fallback} warnings={response.warnings} /><ProfileResult profile={response.data} /></>}
      </Col>
    </Row>
  );
}

function AssetPanel() {
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS);
  const [lookbackDays, setLookbackDays] = useState(252);
  const mutation = useMutation({
    mutationKey: ['risk', 'assets'],
    mutationFn: (input: { symbols: string[]; lookback_days: number }) => client.post<AssetRiskData>('/risk/assets', input),
  });
  const response = mutation.data as AssetRiskResponse | undefined;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card>
        <Space wrap>
          <Select mode="multiple" value={symbols} onChange={setSymbols} options={SYMBOL_OPTIONS} maxCount={4} style={{ minWidth: 320 }} />
          <InputNumber min={60} max={1260} value={lookbackDays} onChange={(value) => value && setLookbackDays(value)} addonAfter="交易日" />
          <Button type="primary" icon={<CalculatorOutlined />} onClick={() => mutation.mutate({ symbols, lookback_days: lookbackDays })} loading={mutation.isPending}>计算资产风险</Button>
        </Space>
      </Card>
      {mutation.isPending && <PageState state="loading" />}
      {mutation.isError && <PageState state="error" error={mutation.error instanceof Error ? mutation.error.message : '资产风险请求失败'} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response && !response.ok && <PageState state="error" error={responseError(response)} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response?.ok && <><StateNotice source={response.meta.source} isFallback={response.meta.is_fallback} warnings={response.warnings} /><AssetResult data={response.data} /></>}
      {!mutation.isPending && !mutation.data && !mutation.isError && <PageState state="empty" emptyDescription="选择标的并开始计算" />}
    </Space>
  );
}

function PortfolioPanel() {
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);
  const [lookbackDays, setLookbackDays] = useState(252);
  const mutation = useMutation({
    mutationKey: ['risk', 'portfolio'],
    mutationFn: (input: { weights_pct: Record<string, number>; lookback_days: number }) => client.post<PortfolioRiskResponse['data']>('/risk/portfolio', input),
  });
  const response = mutation.data as PortfolioRiskResponse | undefined;
  const total = useMemo(() => Object.values(weights).reduce((sum, value) => sum + value, 0), [weights]);
  const analysis = response?.ok ? response.data.portfolio ?? (response.data.portfolio_metrics ? {
    weights_pct: weights,
    portfolio_metrics: response.data.portfolio_metrics,
    correlation_matrix: response.data.correlation_matrix ?? {},
    net_value_curve: response.data.net_value_curve,
    drawdown_curve: response.data.drawdown_curve,
  } : null) : null;
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="固定权重每日再平衡">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Row gutter={[16, 16]}>
            {SYMBOL_OPTIONS.map((item) => <Col xs={24} sm={12} lg={6} key={item.value}><InputNumber addonBefore={item.value} addonAfter="%" min={0} max={100} value={weights[item.value]} onChange={(value) => setWeights((old) => ({ ...old, [item.value]: value ?? 0 }))} style={{ width: '100%' }} /></Col>)}
          </Row>
          <Space wrap>
            <Tag color={Math.abs(total - 100) < 0.000001 ? 'green' : 'red'}>权重合计：{total.toFixed(2)}%</Tag>
            <InputNumber min={60} max={1260} value={lookbackDays} onChange={(value) => value && setLookbackDays(value)} addonAfter="交易日" />
            <Button type="primary" icon={<CalculatorOutlined />} disabled={Math.abs(total - 100) >= 0.000001} loading={mutation.isPending} onClick={() => mutation.mutate({ weights_pct: weights, lookback_days: lookbackDays })}>分析组合风险</Button>
          </Space>
          <Text type="secondary">只使用共同有效收盘价日期；指标描述历史统计，不代表未来表现。</Text>
        </Space>
      </Card>
      {mutation.isPending && <PageState state="loading" />}
      {mutation.isError && <PageState state="error" error={mutation.error instanceof Error ? mutation.error.message : '组合风险请求失败'} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response && !response.ok && <PageState state="error" error={responseError(response)} onRetry={() => mutation.variables && mutation.mutate(mutation.variables)} />}
      {response?.ok && !analysis && <PageState state="partial" warnings={response.warnings} />}
      {response?.ok && analysis && <><StateNotice source={response.meta.source} isFallback={response.meta.is_fallback} warnings={response.warnings} /><PortfolioResult analysis={analysis} /></>}
      {!mutation.isPending && !mutation.data && !mutation.isError && <PageState state="empty" emptyDescription="调整权重后开始组合分析" />}
    </Space>
  );
}

export default function RiskPage() {
  return (
    <div>
      <SectionHeader title="风险实验室" subtitle="用可复现的历史统计理解投资者画像、资产风险与组合波动" />
      <Alert
        type="info"
        showIcon
        message="教学演示边界"
        description="风险评分和指标由确定性 Python 服务计算；历史表现不代表未来收益，VaR/CVaR 不覆盖所有极端事件。"
        style={{ marginBottom: 24 }}
      />
      <Tabs
        items={[
          { key: 'profile', label: '风险画像', children: <ProfilePanel /> },
          { key: 'assets', label: '资产风险', children: <AssetPanel /> },
          { key: 'portfolio', label: '组合风险', children: <PortfolioPanel /> },
        ]}
      />
      <Divider />
      <Text type="secondary">本页面不会执行交易，也不会生成买入、卖出或收益承诺。</Text>
    </div>
  );
}
