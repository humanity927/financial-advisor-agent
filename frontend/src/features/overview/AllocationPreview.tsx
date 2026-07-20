import { useQuery } from '@tanstack/react-query';
import { Card, Table, Descriptions, Tag } from 'antd';
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

  if (isLoading) return <PageState state="loading" />;
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
    <Card title="配置预览">
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="风险等级">{alloc.effective_risk_level}</Descriptions.Item>
        <Descriptions.Item label="风险评分">{alloc.risk_score}</Descriptions.Item>
      </Descriptions>
      <Table
        dataSource={pctData}
        columns={[
          { title: '资产', dataIndex: 'name', key: 'name' },
          { title: '比例', dataIndex: 'pct', key: 'pct', className: 'text-right', render: (v: number) => `${v}%` },
          { title: '金额', dataIndex: 'amount', key: 'amount', className: 'text-right', render: (v: number) => `¥${v.toLocaleString()}` },
        ]}
        rowKey="name"
        pagination={false}
        size="small"
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0}>合计</Table.Summary.Cell>
            <Table.Summary.Cell index={1} className="text-right">100%</Table.Summary.Cell>
            <Table.Summary.Cell index={2} className="text-right">¥{alloc.total_amount_cny.toLocaleString()}</Table.Summary.Cell>
          </Table.Summary.Row>
        )}
      />
      {alloc.constraints_applied.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {alloc.constraints_applied.map((c, i) => (
            <Tag key={i} color="blue" style={{ marginBottom: 4 }}>{c}</Tag>
          ))}
        </div>
      )}
    </Card>
  );
}