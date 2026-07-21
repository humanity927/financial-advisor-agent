import { useCallback, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  InputNumber,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import SectionHeader from '../../components/SectionHeader';
import ProfileForm from '../../components/ProfileForm';
import PageState from '../../components/PageState';
import SourceStamp from '../../components/SourceStamp';
import { client, ApiClientError } from '../../api/client';
import type { PortfolioPlanResult, ProfileInput } from '../../api/types';
import './PortfolioPage.css';

const ASSETS = [
  { key: '现金', label: '现金', color: '#1677ff' },
  { key: '债券', label: '债券', color: '#52c41a' },
  { key: '股票', label: '股票', color: '#fa541c' },
  { key: '黄金', label: '黄金', color: '#d48806' },
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
  amount: number;
}

function labelFor(assetKey: string) {
  return LABEL_BY_KEY.get(assetKey) ?? assetKey;
}

function formatCny(value: number) {
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function deviationTag(value: number | null) {
  if (value === null) {
    return <Tag>未填写</Tag>;
  }
  if (value === 0) {
    return <Tag color="default">持平</Tag>;
  }
  return (
    <Tag color={value > 0 ? 'red' : 'green'}>
      {value > 0 ? '+' : ''}
      {value.toFixed(1)}%
    </Tag>
  );
}

export default function PortfolioPage() {
  const [currentAllocation, setCurrentAllocation] = useState<Record<string, number>>(
    DEFAULT_CURRENT_ALLOCATION,
  );

  const currentTotal = useMemo(
    () => Object.values(currentAllocation).reduce((total, value) => total + Number(value || 0), 0),
    [currentAllocation],
  );
  const currentTotalValid = Math.abs(currentTotal - 100) < 0.01;

  const mutation = useMutation({
    mutationFn: (profile: ProfileInput) =>
      client.post<PortfolioPlanResult>('/portfolio/plan', {
        ...profile,
        current_allocation_pct: currentAllocation,
      }),
  });

  const handleSubmit = useCallback(
    (values: ProfileInput) => {
      mutation.mutate(values);
    },
    [mutation],
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
      amount: plan.allocation_amount_cny[assetKey] ?? 0,
    }));
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
      dataIndex: 'amount',
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
      title: '目标偏离',
      dataIndex: 'deviationPct',
      key: 'deviationPct',
      width: 112,
      render: (value: number | null) => deviationTag(value),
    },
  ];

  const errorMessage =
    mutation.error instanceof ApiClientError
      ? mutation.error.message
      : mutation.error instanceof Error
        ? mutation.error.message
        : '配置规划生成失败，请稍后重试';

  return (
    <div className="portfolio-page">
      <SectionHeader
        title="配置规划"
        subtitle="根据投资者画像生成资产配置比例、金额拆分和目标偏离说明"
      />

      <div className="portfolio-grid">
        <div className="portfolio-stack">
          <ProfileForm onSubmit={handleSubmit} loading={mutation.isPending} />

          <Card className="portfolio-form-card" title="当前配置">
            <Form layout="vertical">
              {ASSETS.map((asset) => (
                <Form.Item label={`${asset.label}比例（%）`} key={asset.key}>
                  <InputNumber
                    min={0}
                    max={100}
                    precision={1}
                    value={currentAllocation[asset.key]}
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
              type={currentTotalValid ? 'success' : 'warning'}
              showIcon
              message={`当前比例合计：${currentTotal.toFixed(1)}%`}
              description="合计为 100% 时，系统会同时计算当前配置与目标配置的偏离。"
            />
          </Card>
        </div>

        <div className="portfolio-stack" data-testid="portfolio-result-panel">
          {!mutation.isPending && !mutation.isError && !mutation.isSuccess && (
            <Card>
              <Empty description="填写左侧画像并确认当前配置后，生成资产配置规划。" />
            </Card>
          )}

          {mutation.isPending && (
            <Card>
              <PageState state="loading" />
            </Card>
          )}

          {mutation.isError && (
            <Card>
              <Alert
                type="error"
                showIcon
                message="配置规划生成失败"
                description={errorMessage}
                action={
                  mutation.variables ? (
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={() => mutation.mutate(mutation.variables as ProfileInput)}
                    >
                      重试
                    </Button>
                  ) : undefined
                }
              />
            </Card>
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

                <div className="portfolio-bars">
                  {rows.map((row) => (
                    <div className="portfolio-bar-row" key={row.key}>
                      <span className="portfolio-bar-name">{row.label}</span>
                      <Progress
                        percent={row.suggestedPct}
                        strokeColor={ASSETS.find((asset) => asset.key === row.key)?.color}
                        showInfo={false}
                      />
                      <span className="portfolio-bar-value">{row.suggestedPct.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card title="比例与金额明细">
                <Table
                  dataSource={rows}
                  columns={columns}
                  rowKey="key"
                  pagination={false}
                  size="small"
                  scroll={{ x: 680 }}
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
                      <Table.Summary.Cell index={4}>偏离合计 0</Table.Summary.Cell>
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
      </div>
    </div>
  );
}
