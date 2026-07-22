import { useQuery } from '@tanstack/react-query';
import { Card, Descriptions, Tag, Skeleton } from 'antd';
import { client } from '../../api/client';
import { queryKeys } from '../../api/keys';
import type { AllocationResult } from '../../api/types';
import PageState from '../../components/PageState';

const DUMMY_PROFILE = {
  amount_cny: 50000,
  horizon_months: 12,
  max_loss_pct: 10,
  income_stability: 'stable' as const,
  experience: 'basic' as const,
  liquidity_need: 'medium' as const,
  emergency_fund_months: 6,
};

export default function AllocationPreview() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: queryKeys.portfolioPlan,
    queryFn: ({ signal }) => client.post<AllocationResult>('/portfolio/plan', DUMMY_PROFILE, signal),
  });

  if (isLoading) {
    return (
      <Card title="配置预览">
        <Skeleton active paragraph={{ rows: 4 }} />
      </Card>
    );
  }

  if (isError || !data?.ok) {
    return <PageState state="error" error={error instanceof Error ? error.message : '配置加载失败'} onRetry={refetch} />;
  }

  const alloc = data.data;
  const pctData = Object.entries(alloc.allocation_pct).map(([name, pct]) => ({
    name,
    pct,
    amount: alloc.allocation_amount_cny[name],
  }));

  return (
    <Card title="配置预览" extra={<Tag>示例画像</Tag>} className="overview-allocation-card">
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="风险等级">{alloc.effective_risk_level}</Descriptions.Item>
        <Descriptions.Item label="风险评分">{alloc.risk_score}</Descriptions.Item>
      </Descriptions>
      <div className="overview-allocation-grid">
        {pctData.map((item) => (
          <div key={item.name}>
            <span>{item.name}</span>
            <strong>{item.pct}%</strong>
            <small>¥{item.amount.toLocaleString()}</small>
          </div>
        ))}
      </div>
      <div className="overview-allocation-total">
        <span>合计</span>
        <strong>100% · ¥{alloc.total_amount_cny.toLocaleString()}</strong>
      </div>
      {alloc.constraints_applied.length > 0 && (
        <div className="overview-allocation-constraints">
          {alloc.constraints_applied.map((c, i) => (
            <Tag key={i} color="blue" style={{ marginBottom: 4 }}>{c}</Tag>
          ))}
        </div>
      )}
    </Card>
  );
}
