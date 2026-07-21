import { ArrowUpOutlined, ArrowDownOutlined, MinusOutlined } from '@ant-design/icons';

type MetricType = 'price' | 'pct' | 'money';

interface MetricValueProps {
  value: number;
  type?: MetricType;
  precision?: number;
  prefix?: string;
  suffix?: string;
}

function formatMoney(v: number): string {
  if (Math.abs(v) >= 10_000) {
    return (v / 10_000).toFixed(2) + '万';
  }
  return v.toFixed(2);
}

export default function MetricValue({ value, type = 'price', precision, prefix, suffix }: MetricValueProps) {
  const isUp = value > 0;
  const isDown = value < 0;

  let formatted: string;
  if (type === 'money') {
    formatted = formatMoney(value);
  } else if (type === 'pct') {
    formatted = `${value >= 0 ? '+' : ''}${value.toFixed(precision ?? 2)}%`;
  } else {
    formatted = value.toFixed(precision ?? 4);
  }

  return (
    <span className={isUp ? 'text-up' : isDown ? 'text-down' : ''}>
      {prefix}{formatted}{suffix}
      {' '}
      {isUp ? <ArrowUpOutlined /> : isDown ? <ArrowDownOutlined /> : <MinusOutlined />}
      {type === 'money' && ' 元'}
    </span>
  );
}