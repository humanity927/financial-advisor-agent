import { Spin, Empty, Alert, Button, Card } from 'antd';
import { ReloadOutlined, WarningOutlined } from '@ant-design/icons';
import SourceStamp from './SourceStamp';
import type { ReactNode } from 'react';

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
      <Card>
        <Spin tip="加载中..." style={{ display: 'flex', justifyContent: 'center', padding: 64 }}>
          <div style={{ height: 1 }} />
        </Spin>
      </Card>
    );
  }

  if (state === 'empty') {
    return (
      <Card>
        <Empty description={emptyDescription ?? '暂无数据'} />
      </Card>
    );
  }

  if (state === 'error') {
    return (
      <Card>
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={error ?? '请求异常，请稍后重试'}
          action={
            onRetry ? (
              <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
                重试
              </Button>
            ) : null
          }
        />
      </Card>
    );
  }

  if (state === 'fixture') {
    return (
      <>
        <Alert
          type="warning"
          showIcon
          icon={<WarningOutlined />}
          message="演示模式"
          description="当前使用演示数据，非实时行情。请配置模型 API Key 以获取完整功能。"
          style={{ marginBottom: 16 }}
        />
        {children}
      </>
    );
  }

  if (state === 'partial') {
    return (
      <>
        <Alert
          type="warning"
          showIcon
          message="部分数据不可用"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {warnings?.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          }
          style={{ marginBottom: 16 }}
        />
        {children}
      </>
    );
  }

  // success
  return (
    <>
      {isFallback && (
        <Alert
          type="warning"
          showIcon
          message="回退数据"
          description="部分数据来自回退源，可能不是最新"
          style={{ marginBottom: 16 }}
        />
      )}
      {warnings && warnings.length > 0 && (
        <Alert
          type="info"
          showIcon
          message={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          }
          style={{ marginBottom: 16 }}
        />
      )}
      <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        {source && <SourceStamp source={source} isFallback={isFallback} />}
      </div>
      {children}
    </>
  );
}