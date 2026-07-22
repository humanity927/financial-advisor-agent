import { Alert, Button, Empty, Spin } from 'antd';
import { RefreshCw, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import SourceStamp from './SourceStamp';

type PageStateVariant = 'loading' | 'empty' | 'error' | 'fixture' | 'partial' | 'success';

interface PageStateProps {
  state: PageStateVariant;
  error?: string;
  warnings?: string[];
  source?: string;
  isFallback?: boolean;
  onRetry?: () => void;
  emptyDescription?: string;
  children?: ReactNode;
}

export default function PageState({
  state,
  error,
  warnings,
  source,
  isFallback,
  onRetry,
  emptyDescription,
  children,
}: PageStateProps) {
  if (state === 'loading') {
    return (
      <div className="page-state page-state-loading" role="status" aria-live="polite">
        <span className="page-state-loading-copy"><Spin /><span>加载中...</span></span>
      </div>
    );
  }

  if (state === 'empty') {
    return (
      <div className="page-state">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyDescription ?? '暂无数据'} />
      </div>
    );
  }

  if (state === 'error') {
    return (
      <div className="page-state">
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={error ?? '请求异常，请稍后重试'}
          action={onRetry ? (
            <Button size="small" icon={<RefreshCw size={14} />} onClick={onRetry}>
              重试
            </Button>
          ) : null}
        />
      </div>
    );
  }

  if (state === 'fixture') {
    return (
      <>
        <Alert
          className="page-state-notice"
          type="warning"
          showIcon
          icon={<TriangleAlert size={16} />}
          message="演示数据 / 非实时数据"
          description="当前结果来自测试演示源，不代表实时市场状态。"
        />
        {children}
      </>
    );
  }

  if (state === 'partial') {
    return (
      <>
        <Alert
          className="page-state-notice"
          type="warning"
          showIcon
          message="部分数据不可用"
          description={<ul>{warnings?.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
        />
        {children}
      </>
    );
  }

  return (
    <>
      {isFallback && (
        <Alert
          className="page-state-notice"
          type="warning"
          showIcon
          message="回退数据"
          description="部分数据来自回退源，可能不是最新状态。"
        />
      )}
      {warnings && warnings.length > 0 && (
        <Alert
          className="page-state-notice"
          type="info"
          showIcon
          message={<ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
        />
      )}
      {source && <div className="page-state-source"><SourceStamp source={source} isFallback={isFallback} /></div>}
      {children}
    </>
  );
}
