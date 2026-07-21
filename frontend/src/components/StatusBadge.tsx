import { Tag } from 'antd';

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  healthy: { color: 'green', label: '正常' },
  warning: { color: 'orange', label: '注意' },
  error: { color: 'red', label: '异常' },
  offline: { color: 'default', label: '离线' },
};

interface StatusBadgeProps {
  status: 'healthy' | 'warning' | 'error' | 'offline';
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.offline;
  return <Tag color={cfg.color}>{cfg.label}</Tag>;
}