import { useCallback, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  InputNumber,
  Row,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { BarChart3, PieChart, RefreshCcw } from 'lucide-react';
import SectionHeader from '../../components/SectionHeader';
import ProfileForm from '../../components/ProfileForm';
import PageState from '../../components/PageState';
import SourceStamp from '../../components/SourceStamp';
import { client, ApiClientError } from '../../api/client';
import type { PortfolioPlanResult, ProfileInput } from '../../api/types';
import './PortfolioPage.css';
import { useWorkspace } from '../../app/WorkspaceContext';
import WorkspaceLayout from '../../components/WorkspaceLayout';

const ASSETS = [
  { key: '现金', label: '现金', color: '#2B7BD6' },
  { key: '债券', label: '债券', color: '#52c41a' },
  { key: '股票', label: '股票', color: '#CF1322' },
  { key: '黄金', label: '黄金', color: '#D4883A' },
] as const;

const DEFAULT_CURRENT_ALLOCATION: Record<string, number> = {
  现金: 30,
  债券: 35,
  股票: 25,
  黄金: 10,
};

const LABEL_BY_KEY = new Map<string, string>(ASSETS.map((asset) => [asset.key, asset.label]));

interface AllocationRow {
  key: string;
  label: string;
  suggestedPct: number;
  currentPct: number | null;
  deviationPct: number | null;
  suggestedAmount: number;
  currentAmount: number | null;
  deviationAmount: number | null;
}

interface PortfolioMutationInput {
  profile: ProfileInput;
  currentAllocationPct: Record<string, number> | null;
}

function labelFor(assetKey: string) {
  return LABEL_BY_KEY.get(assetKey) ?? assetKey;
}

function formatCny(value: number) {
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSignedCny(value: number) {
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  return `${sign}¥${Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function deviationTag(value: number | null) {
  if (value === null) {
    return <Tag>未填写</Tag>;
  }
  if (value === 0) {
    return <Tag color="default">持平</Tag>;
  }
  return (
    <Tag color={value > 0 ? 'geekblue' : 'gold'}>
      {value > 0 ? '+' : ''}
      {value.toFixed(1)}%
    </Tag>
  );
}

export default function PortfolioPage() {
  const workspace = useWorkspace();
  const [compareCurrent, setCompareCurrent] = useState(true);
  const [currentAllocation, setCurrentAllocation] = useState<Record<string, number>>(
    workspace.currentAllocationPct ?? DEFAULT_CURRENT_ALLOCATION,
  );

  const currentTotal = useMemo(
    () => Object.values(currentAllocation).reduce((total, value) => total + Number(value || 0), 0),
    [currentAllocation],
  );
  const currentTotalValid = Math.abs(currentTotal - 100) < 0.01;

  const mutation = useMutation({
    mutationFn: ({ profile, currentAllocationPct }: PortfolioMutationInput) =>
      client.post<PortfolioPlanResult>('/portfolio/plan', {
        ...profile,
        current_allocation_pct: currentAllocationPct,
      }),
  });

  const handleSubmit = useCallback(
    (values: ProfileInput) => {
      if (compareCurrent && !currentTotalValid) {
        return;
      }
      mutation.mutate({
        profile: values,
        currentAllocationPct: compareCurrent ? { ...currentAllocation } : null,
      });
      workspace.patchProfile(values);
      workspace.setCurrentAllocationPct(compareCurrent ? { ...currentAllocation } : null);
    },
    [compareCurrent, currentAllocation, currentTotalValid, mutation, workspace],
  );

  const plan = mutation.data?.data;
  const rows = useMemo<AllocationRow[]>(() => {
    if (!plan) {
      return [];
    }
    return Object.entries(plan.allocation_pct).map(([assetKey, pct]) => ({
      key: assetKey,
      label: labelFor(assetKey),
      suggestedPct: pct,
      currentPct: plan.current_allocation_pct?.[assetKey] ?? null,
      deviationPct: plan.allocation_deviation_pct?.[assetKey] ?? null,
      suggestedAmount: plan.allocation_amount_cny[assetKey] ?? 0,
      currentAmount: plan.current_allocation_amount_cny?.[assetKey] ?? null,
      deviationAmount: plan.allocation_deviation_amount_cny?.[assetKey] ?? null,
    }));
  }, [plan]);

  const pieOption = useMemo<EChartsOption | null>(() => {
    if (!plan) {
      return null;
    }
    return {
      color: ASSETS.map((asset) => asset.color),
      tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
      legend: { bottom: 0, itemWidth: 12, itemHeight: 8 },
      series: [
        {
          type: 'pie',
          radius: ['48%', '72%'],
          center: ['50%', '43%'],
          avoidLabelOverlap: true,
          label: {
            position: 'inside',
            formatter: '{c}%',
            color: '#FFFFFF',
            fontWeight: 600,
          },
          labelLine: { show: false },
          data: ASSETS.map((asset) => ({
            name: asset.label,
            value: plan.allocation_pct[asset.key] ?? 0,
          })),
        },
      ],
    };
  }, [plan]);

  const comparisonOption = useMemo<EChartsOption | null>(() => {
    if (!plan) {
      return null;
    }
    const series: EChartsOption['series'] = [
      {
        name: '建议比例',
        type: 'bar',
        data: ASSETS.map((asset) => plan.allocation_pct[asset.key] ?? 0),
        itemStyle: { color: '#2B7BD6' },
        barMaxWidth: 22,
      },
    ];
    if (plan.current_allocation_pct) {
      series.unshift({
        name: '当前比例',
        type: 'bar',
        data: ASSETS.map((asset) => plan.current_allocation_pct?.[asset.key] ?? 0),
        itemStyle: { color: '#98A2B3' },
        barMaxWidth: 22,
      });
    }
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value) => `${value}%` },
      legend: { top: 0 },
      grid: { left: 56, right: 20, top: 42, bottom: 30 },
      xAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      yAxis: { type: 'category', data: ASSETS.map((asset) => asset.label) },
      series,
    };
  }, [plan]);

  const columns: TableColumnsType<AllocationRow> = [
    { title: '资产类别', dataIndex: 'label', key: 'label', width: 96 },
    {
      title: '建议比例',
      dataIndex: 'suggestedPct',
      key: 'suggestedPct',
      className: 'text-right',
      width: 112,
      render: (value: number) => `${value.toFixed(1)}%`,
    },
    {
      title: '建议金额',
      dataIndex: 'suggestedAmount',
      key: 'amount',
      className: 'text-right',
      width: 140,
      render: (value: number) => formatCny(value),
    },
    {
      title: '当前比例',
      dataIndex: 'currentPct',
      key: 'currentPct',
      className: 'text-right',
      width: 112,
      render: (value: number | null) => (value === null ? '-' : `${value.toFixed(1)}%`),
    },
    {
      title: '当前金额',
      dataIndex: 'currentAmount',
      key: 'currentAmount',
      className: 'text-right',
      width: 140,
      render: (value: number | null) => (value === null ? '-' : formatCny(value)),
    },
    {
      title: '目标偏离',
      dataIndex: 'deviationPct',
      key: 'deviationPct',
      width: 112,
      render: (value: number | null) => deviationTag(value),
    },
    {
      title: '目标金额差额',
      dataIndex: 'deviationAmount',
      key: 'deviationAmount',
      className: 'text-right',
      width: 152,
      render: (value: number | null) => (value === null ? '-' : formatSignedCny(value)),
    },
  ];

  const errorMessage =
    mutation.error instanceof ApiClientError
      ? mutation.error.message
      : mutation.error instanceof Error
        ? mutation.error.message
        : '配置规划生成失败，请稍后重试';

  return (
    <div className="page-layout portfolio-page">
      <SectionHeader
        title="配置规划"
        subtitle="根据投资者画像生成资产配置比例、金额拆分和目标偏离说明"
      />

      <WorkspaceLayout
        className="portfolio-grid"
        sidebar={(
        <div className="workspace-sidebar-stack">
          <ProfileForm
            onSubmit={handleSubmit}
            initialValues={workspace.profile}
            onValuesChange={workspace.patchProfile}
            loading={mutation.isPending}
            submitLabel="生成配置方案"
            submitTestId="portfolio-submit"
            submitDisabled={compareCurrent && !currentTotalValid}
          />

          <Card
            className="portfolio-form-card"
            title="当前配置"
            extra={
              <Space size="small">
                <Typography.Text type="secondary">偏离对比</Typography.Text>
                <Switch
                  aria-label="参与当前配置对比"
                  checked={compareCurrent}
                  onChange={setCompareCurrent}
                />
              </Space>
            }
          >
            <Form layout="vertical">
              {ASSETS.map((asset) => (
                <Form.Item label={`${asset.label}比例（%）`} key={asset.key}>
                  <InputNumber
                    min={0}
                    max={100}
                    precision={1}
                    value={currentAllocation[asset.key]}
                    disabled={!compareCurrent}
                    aria-label={`${asset.label}比例`}
                    onChange={(value) =>
                      setCurrentAllocation((prev) => ({
                        ...prev,
                        [asset.key]: Number(value ?? 0),
                      }))
                    }
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              ))}
            </Form>
            <Alert
              type={!compareCurrent ? 'info' : currentTotalValid ? 'success' : 'warning'}
              showIcon
              message={
                compareCurrent
                  ? `当前比例合计：${currentTotal.toFixed(1)}%`
                  : '未纳入当前配置对比'
              }
            />
          </Card>
        </div>
        )}
      >

        <div className="workspace-main-stack" data-testid="portfolio-result-panel">
          {!mutation.isPending && !mutation.isError && !mutation.isSuccess && (
            <PageState state="empty" emptyDescription="填写左侧画像并确认当前配置后，生成资产配置规划。" />
          )}

          {mutation.isPending && <PageState state="loading" />}

          {mutation.isError && (
            <div className="page-state">
              <Alert
                type="error"
                showIcon
                message="配置规划生成失败"
                description={errorMessage}
                action={
                  mutation.variables ? (
                    <Button
                      size="small"
                      icon={<RefreshCcw size={14} />}
                      onClick={() => mutation.mutate(mutation.variables)}
                    >
                      重试
                    </Button>
                  ) : undefined
                }
              />
            </div>
          )}

          {mutation.isSuccess && plan && (
            <>
              <Card>
                <div className="portfolio-result-header">
                  <Space wrap>
                    <Typography.Title level={4} style={{ margin: 0 }}>
                      资产配置方案
                    </Typography.Title>
                    <Tag color="blue">{plan.method}</Tag>
                  </Space>
                  <SourceStamp
                    source={mutation.data.meta.source}
                    isFallback={mutation.data.meta.is_fallback}
                  />
                  <Typography.Text type="secondary">
                    计算时间：{mutation.data.meta.as_of}
                  </Typography.Text>
                </div>

                <div className="portfolio-risk-summary">
                  <div className="portfolio-risk-item">
                    <span>风险评分</span>
                    <strong>{plan.risk_score}</strong>
                  </div>
                  <div className="portfolio-risk-item">
                    <span>画像等级</span>
                    <strong>{plan.scored_risk_level}</strong>
                  </div>
                  <div className="portfolio-risk-item">
                    <span>有效等级</span>
                    <strong>{plan.effective_risk_level}</strong>
                  </div>
                </div>

                <div className="portfolio-visual-grid">
                  <section className="portfolio-chart-panel" data-testid="portfolio-allocation-chart">
                    <h3><PieChart size={17} />建议配置结构</h3>
                    {pieOption && <ReactECharts option={pieOption} className="portfolio-chart" />}
                  </section>
                  <section className="portfolio-chart-panel" data-testid="portfolio-comparison-chart">
                    <h3><BarChart3 size={17} />当前与建议对比</h3>
                    {comparisonOption && (
                      <ReactECharts option={comparisonOption} className="portfolio-chart" />
                    )}
                  </section>
                </div>
              </Card>

              <Card title="比例与金额明细">
                <Table
                  dataSource={rows}
                  columns={columns}
                  rowKey="key"
                  pagination={false}
                  size="small"
                  scroll={{ x: 1040 }}
                  summary={() => (
                    <Table.Summary.Row>
                      <Table.Summary.Cell index={0}>合计</Table.Summary.Cell>
                      <Table.Summary.Cell index={1} className="text-right">100.0%</Table.Summary.Cell>
                      <Table.Summary.Cell index={2} className="text-right">
                        {formatCny(plan.total_amount_cny)}
                      </Table.Summary.Cell>
                      <Table.Summary.Cell index={3} className="text-right">
                        {plan.current_allocation_pct ? '100.0%' : '-'}
                      </Table.Summary.Cell>
                      <Table.Summary.Cell index={4} className="text-right">
                        {plan.current_allocation_amount_cny
                          ? formatCny(plan.total_amount_cny)
                          : '-'}
                      </Table.Summary.Cell>
                      <Table.Summary.Cell index={5}>比例差额 0</Table.Summary.Cell>
                      <Table.Summary.Cell index={6}>金额差额 0</Table.Summary.Cell>
                    </Table.Summary.Row>
                  )}
                />
              </Card>

              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card title="调整步骤">
                    <ol className="portfolio-list">
                      {plan.adjustment_steps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card title="方案理由">
                    <ul className="portfolio-list">
                      {plan.rationale.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </Card>
                </Col>
              </Row>

              {plan.constraints_applied.length > 0 && (
                <Card title="约束条件">
                  <Space wrap>
                    {plan.constraints_applied.map((constraint) => (
                      <Tag color="orange" key={constraint}>
                        {constraint}
                      </Tag>
                    ))}
                  </Space>
                </Card>
              )}

              {mutation.data.warnings.length > 0 && (
                <Alert
                  type="info"
                  showIcon
                  message="方案说明"
                  description={
                    <ul className="portfolio-list">
                      {mutation.data.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                    </ul>
                  }
                />
              )}

              <Alert
                className="portfolio-warning"
                type="warning"
                showIcon
                message="风险提示"
                description="本页面仅展示课程系统生成的资产配置比例和偏离解释，不提供买卖指令，也不承诺收益。"
              />
            </>
          )}
        </div>
      </WorkspaceLayout>
    </div>
  );
}
