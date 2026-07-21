import { useEffect } from 'react';
import { Form, InputNumber, Select, Button, Card, Typography, Space } from 'antd';
import type { CatalogSymbol, ProfileInput } from '../api/types';

const { Title } = Typography;

interface ProfileFormProps {
  onSubmit: (values: ProfileInput) => void;
  loading?: boolean;
  submitLabel?: string;
  submitTestId?: string;
  submitDisabled?: boolean;
  symbols?: string[];
  onSymbolsChange?: (symbols: string[]) => void;
  initialValues?: Partial<ProfileInput>;
  onValuesChange?: (values: Partial<ProfileInput>) => void;
  symbolOptions?: CatalogSymbol[];
}

const INCOME_OPTIONS = [
  { value: 'unstable', label: '不稳定' },
  { value: 'stable', label: '稳定' },
  { value: 'very_stable', label: '非常稳定' },
];

const EXPERIENCE_OPTIONS = [
  { value: 'none', label: '无经验' },
  { value: 'basic', label: '基础经验' },
  { value: 'regular', label: '定期投资' },
  { value: 'expert', label: '专业' },
];

const LIQUIDITY_OPTIONS = [
  { value: 'high', label: '高（随时可能需要）' },
  { value: 'medium', label: '中等' },
  { value: 'low', label: '低（长期持有）' },
];

const SYMBOL_OPTIONS = [
  { value: '510300', label: '510300 · 沪深300ETF' },
  { value: '511010', label: '511010 · 国债ETF' },
  { value: '518880', label: '518880 · 黄金ETF' },
  { value: '511880', label: '511880 · 货币ETF' },
];

export default function ProfileForm({
  onSubmit,
  loading = false,
  submitLabel = '生成报告',
  submitTestId,
  submitDisabled = false,
  symbols,
  onSymbolsChange,
  initialValues,
  onValuesChange,
  symbolOptions,
}: ProfileFormProps) {
  const [form] = Form.useForm<ProfileInput>();

  useEffect(() => {
    if (initialValues) form.setFieldsValue(initialValues);
  }, [form, initialValues]);

  const handleFinish = (values: ProfileInput) => {
    onSubmit(values);
  };

  return (
    <Card>
      <Title level={5} style={{ marginTop: 0 }}>投资者画像</Title>
      <Form
        form={form}
        layout="vertical"
        onFinish={handleFinish}
        onValuesChange={(_, values) => onValuesChange?.(values)}
        initialValues={{
          amount_cny: 50000,
          horizon_months: 12,
          max_loss_pct: 10,
          income_stability: 'stable' as const,
          experience: 'basic' as const,
          liquidity_need: 'medium' as const,
          emergency_fund_months: 6,
          ...initialValues,
        }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          <Form.Item label="投资金额（元）" name="amount_cny" rules={[{ required: true, type: 'number', min: 1, max: 1_000_000_000 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={1_000_000_000} />
          </Form.Item>

          <Form.Item label="投资期限（月）" name="horizon_months" rules={[{ required: true, type: 'number', min: 1, max: 600 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={600} />
          </Form.Item>

          <Form.Item label="最大可承受亏损（%）" name="max_loss_pct" rules={[{ required: true, type: 'number', min: 0, max: 100 }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={100} />
          </Form.Item>

          <Form.Item label="收入稳定性" name="income_stability" rules={[{ required: true }]}>
            <Select options={INCOME_OPTIONS} />
          </Form.Item>

          <Form.Item label="投资经验" name="experience" rules={[{ required: true }]}>
            <Select options={EXPERIENCE_OPTIONS} />
          </Form.Item>

          <Form.Item label="流动性需求" name="liquidity_need" rules={[{ required: true }]}>
            <Select options={LIQUIDITY_OPTIONS} />
          </Form.Item>

          <Form.Item label="应急资金可覆盖月数" name="emergency_fund_months" rules={[{ required: true, type: 'number', min: 0, max: 120 }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={120} />
          </Form.Item>

          {onSymbolsChange && (
            <Form.Item label="关注标的（可多选）">
              <Select
                mode="multiple"
                value={symbols}
                onChange={onSymbolsChange}
                options={symbolOptions?.map((item) => ({
                  value: item.symbol,
                  label: `${item.symbol} · ${item.name}`,
                })) ?? SYMBOL_OPTIONS}
                placeholder="选择关注标的"
                maxCount={8}
              />
            </Form.Item>
          )}

          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              disabled={submitDisabled}
              block
              data-testid={submitTestId}
            >
              {submitLabel}
            </Button>
          </Form.Item>
        </Space>
      </Form>
    </Card>
  );
}
