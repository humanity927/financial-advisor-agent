import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SourceStamp from '../components/SourceStamp';
import StatusBadge from '../components/StatusBadge';
import MetricValue from '../components/MetricValue';
import SectionHeader from '../components/SectionHeader';

describe('SourceStamp', () => {
  it('renders fixture label with orange tag', () => {
    render(<SourceStamp source="fixture" />);
    expect(screen.getByText('演示数据')).toBeInTheDocument();
  });

  it('renders akshare label', () => {
    render(<SourceStamp source="akshare" />);
    expect(screen.getByText('实时数据')).toBeInTheDocument();
  });

  it('shows warning indicator when isFallback', () => {
    render(<SourceStamp source="cache" isFallback />);
    const tag = screen.getByText(/缓存数据/);
    expect(tag).toBeInTheDocument();
  });
});

describe('StatusBadge', () => {
  it('renders healthy status', () => {
    render(<StatusBadge status="healthy" />);
    expect(screen.getByText('正常')).toBeInTheDocument();
  });

  it('renders error status', () => {
    render(<StatusBadge status="error" />);
    expect(screen.getByText('异常')).toBeInTheDocument();
  });

  it('renders offline fallback', () => {
    render(<StatusBadge status="offline" />);
    expect(screen.getByText('离线')).toBeInTheDocument();
  });
});

describe('MetricValue', () => {
  it('formats percentage with + sign for positive', () => {
    render(<MetricValue value={2.5} type="pct" />);
    expect(screen.getByText('+2.50%')).toBeInTheDocument();
  });

  it('formats percentage with - for negative', () => {
    render(<MetricValue value={-1.3} type="pct" />);
    expect(screen.getByText('-1.30%')).toBeInTheDocument();
  });

  it('formats price with 4 decimals', () => {
    render(<MetricValue value={4.183} type="price" />);
    expect(screen.getByText('4.1830')).toBeInTheDocument();
  });
});

describe('SectionHeader', () => {
  it('renders title', () => {
    render(<SectionHeader title="总览" />);
    expect(screen.getByText('总览')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    render(<SectionHeader title="总览" subtitle="系统健康" />);
    expect(screen.getByText('系统健康')).toBeInTheDocument();
  });
});