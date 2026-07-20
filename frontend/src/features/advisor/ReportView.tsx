import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import { Typography } from 'antd';

const { Title, Paragraph, Text } = Typography;

interface ReportViewProps {
  content: string;
}

export default function ReportView({ content }: ReportViewProps) {
  return (
    <div className="report-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          h1: ({ children }) => <Title level={3}>{children}</Title>,
          h2: ({ children }) => <Title level={4} style={{ marginTop: 20 }}>{children}</Title>,
          h3: ({ children }) => <Title level={5}>{children}</Title>,
          p: ({ children }) => <Paragraph style={{ lineHeight: 1.8 }}>{children}</Paragraph>,
          strong: ({ children }) => <Text strong>{children}</Text>,
          table: ({ children }) => (
            <div style={{ overflowX: 'auto', marginBottom: 16 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th style={{ border: '1px solid #D9E0E5', padding: '8px 12px', background: '#F4F6F7', textAlign: 'left', fontWeight: 600 }}>{children}</th>
          ),
          td: ({ children }) => (
            <td style={{ border: '1px solid #D9E0E5', padding: '8px 12px' }}>{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}