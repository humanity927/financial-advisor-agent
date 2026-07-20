import { Tag } from 'antd';
import { Clock } from 'lucide-react';

export default function TopBar() {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 224,
        right: 0,
        height: 54,
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        background: '#fff',
        borderBottom: '1px solid var(--color-border)',
        zIndex: 99,
        gap: 16,
      }}
    >
      <Tag color="blue" icon={<Clock size={14} />}>
        fixture 模式
      </Tag>
      <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
        数据来源：演示数据
      </span>
      <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
        Agent 状态：未连接
      </span>
    </div>
  );
}