import { Typography } from 'antd';
import type { ReactNode } from 'react';

const { Title } = Typography;

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export default function SectionHeader({ title, subtitle, actions }: SectionHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 24,
      }}
    >
      <div>
        <Title level={4} style={{ margin: 0 }}>{title}</Title>
        {subtitle && (
          <span style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>{subtitle}</span>
        )}
      </div>
      {actions && <div>{actions}</div>}
    </div>
  );
}