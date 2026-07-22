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
    <header className="section-header">
      <div className="section-header-copy">
        <Title level={3} className="section-header-title">{title}</Title>
        {subtitle && <span className="section-header-subtitle">{subtitle}</span>}
      </div>
      {actions && <div className="section-header-actions">{actions}</div>}
    </header>
  );
}
