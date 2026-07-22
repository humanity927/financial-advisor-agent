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
          h2: ({ children }) => <Title level={4}>{children}</Title>,
          h3: ({ children }) => <Title level={5}>{children}</Title>,
          p: ({ children }) => <Paragraph>{children}</Paragraph>,
          strong: ({ children }) => <Text strong>{children}</Text>,
          table: ({ children }) => (
            <div className="report-table-wrap">
              <table className="report-table">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th>{children}</th>
          ),
          td: ({ children }) => (
            <td>{children}</td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
