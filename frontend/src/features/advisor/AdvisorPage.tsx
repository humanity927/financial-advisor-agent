import { useState, useCallback, useRef } from 'react';
import { Card, Alert, Tag, Divider, Button } from 'antd';
import { Bot, Clock3, RefreshCw } from 'lucide-react';
import { useMutation } from '@tanstack/react-query';
import SectionHeader from '../../components/SectionHeader';
import PageState from '../../components/PageState';
import ProfileForm from '../../components/ProfileForm';
import SourceStamp from '../../components/SourceStamp';
import ReportView from './ReportView';
import { client, ApiClientError } from '../../api/client';
import type { ProfileInput } from '../../api/types';
import type { ChatToolCall } from '../../api/types';
import { useWorkspace } from '../../app/WorkspaceContext';
import WorkspaceLayout from '../../components/WorkspaceLayout';

const REPORT_TIMEOUT_MS = 130_000;

export default function AdvisorPage() {
  const workspace = useWorkspace();
  const [symbols, setSymbols] = useState<string[]>(workspace.selectedSymbols);
  const abortRef = useRef<AbortController | null>(null);

  const mutation = useMutation({
    mutationFn: async (profile: ProfileInput) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const timeoutId = setTimeout(() => controller.abort(), REPORT_TIMEOUT_MS);
      try {
        const res = await client.post<{ content: string; source: string; as_of: string; is_fallback: boolean; warnings: string[]; tool_calls: ChatToolCall[] }>(
          '/advisor/report',
          { ...profile, symbols },
          controller.signal,
        );
        return res;
      } finally {
        clearTimeout(timeoutId);
      }
    },
  });

  const handleSubmit = useCallback(
    (values: ProfileInput) => {
      workspace.patchProfile(values);
      mutation.mutate(values);
    },
    [mutation, workspace],
  );

  const handleRetry = useCallback(() => {
    if (mutation.variables) {
      mutation.mutate(mutation.variables);
    }
  }, [mutation]);

  const isLoading = mutation.isPending;
  const isTimeout = mutation.isError && mutation.error instanceof DOMException && mutation.error.name === 'AbortError';
  const isApiError = mutation.isError && !isTimeout;
  const isNoModel =
    mutation.isError &&
    mutation.error instanceof ApiClientError &&
    (mutation.error.code === 'model_unavailable' ||
      mutation.error.code === 'model_configuration_missing' ||
      mutation.error.code === 'model_auth_failed');

  return (
    <div className="page-layout report-page">
      <SectionHeader title="正式咨询报告" subtitle="基于完整画像与四类 MCP 工具结果生成可核验报告" />

      <WorkspaceLayout
        sidebar={(
          <ProfileForm
            onSubmit={handleSubmit}
            loading={isLoading}
            symbols={symbols}
            onSymbolsChange={setSymbols}
            symbolOptions={workspace.watchedSymbols}
            initialValues={workspace.profile}
            onValuesChange={workspace.patchProfile}
          />
        )}
      >
          {!mutation.isError && !mutation.isSuccess && !mutation.isPending && (
            <PageState state="empty" emptyDescription="填写左侧画像表单，点击「生成报告」开始咨询" />
          )}

          {mutation.isPending && <PageState state="loading" />}

          {isTimeout && (
            <div className="page-state">
              <Alert
                type="warning"
                showIcon
                message="报告生成超时"
                description="当前请求超过 130 秒未返回，可能是模型响应较慢或网络异常。请稍后重试。"
                action={
                  <Button size="small" icon={<RefreshCw size={14} />} onClick={handleRetry}>
                    重试
                  </Button>
                }
              />
            </div>
          )}

          {isNoModel && (
            <div className="page-state">
              <Alert
                type="info"
                showIcon
                icon={<Bot size={16} />}
                message="Agent 暂不可用"
                description="模型 API Key 未配置或服务暂不可用。您仍可使用行情、风险与配置页面进行参考。"
              />
            </div>
          )}

          {isApiError && !isNoModel && (
            <div className="page-state">
              <Alert
                type="error"
                showIcon
                message="报告生成失败"
                description={mutation.error instanceof ApiClientError ? mutation.error.message : '请求异常，请稍后重试'}
                action={
                  <Button size="small" icon={<RefreshCw size={14} />} onClick={handleRetry}>
                    重试
                  </Button>
                }
              />
            </div>
          )}

          {mutation.isSuccess && (!mutation.data?.data?.content || mutation.data.data.content.trim().length === 0) && (
            <div className="page-state">
              <Alert
                type="warning"
                showIcon
                message="报告内容为空"
                description="模型返回了空的咨询报告。"
                action={
                  <Button size="small" icon={<RefreshCw size={14} />} onClick={handleRetry}>
                    重新生成
                  </Button>
                }
              />
            </div>
          )}

          {mutation.isSuccess && mutation.data?.data?.content && mutation.data.data.content.trim().length > 0 && (
            <Card>
              <div className="report-meta-row">
                <SourceStamp
                  source={mutation.data.data.source || 'system'}
                  isFallback={mutation.data.data.is_fallback}
                />
                {mutation.data.data.as_of && (
                  <Tag icon={<Clock3 size={13} />}>{mutation.data.data.as_of}</Tag>
                )}
              </div>

              <Alert
                type="warning"
                showIcon
                message="风险提示"
                description="本报告由 AI 生成，仅供参考。历史表现不代表未来收益，配置建议不构成投资建议。投资有风险，决策需谨慎。"
                style={{ marginBottom: 16 }}
              />

              <div className="report-tool-row">
                {mutation.data.data.tool_calls.map((call) => (
                  <Tag color={call.ok ? 'success' : 'error'} key={`${call.tool}-${call.called_at}`}>
                    {call.tool} · {call.source}
                  </Tag>
                ))}
              </div>

              <ReportView content={mutation.data.data.content} />

              <Divider />

              <Alert
                type="info"
                showIcon
                message="免责声明"
                description="本系统仅用于课程教学和软件工程演示。输出内容不构成任何投资、法律或税务建议。"
              />
            </Card>
          )}
      </WorkspaceLayout>
    </div>
  );
}
