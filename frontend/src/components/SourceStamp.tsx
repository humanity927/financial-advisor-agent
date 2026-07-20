import { Tag } from 'antd';

const SOURCE_LABELS: Record<string, string> = {
  akshare: '实时数据',
  cache: '缓存数据',
  fixture: '演示数据',
  system: '系统',
  mixed: '多源',
};

const SOURCE_COLORS: Record<string, string> = {
  akshare: 'green',
  cache: 'blue',
  fixture: 'orange',
  system: 'default',
  mixed: 'geekblue',
};

interface SourceStampProps {
  source: string;
  isFallback?: boolean;
}

export default function SourceStamp({ source, isFallback }: SourceStampProps) {
  const label = SOURCE_LABELS[source] ?? source;
  const color = SOURCE_COLORS[source] ?? 'default';

  return (
    <Tag color={color}>
      {label}
      {isFallback && ' ⚠'}
    </Tag>
  );
}