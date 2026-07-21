import { useState, useCallback, useRef } from 'react';
import { Row, Col, Card, Alert, Tag, Empty, Divider, Button } from 'antd';
import { ReloadOutlined, RobotOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import SectionHeader from '../../components/SectionHeader';
import PageState from '../../components/PageState';
import ProfileForm from '../../components/ProfileForm';
import SourceStamp from '../../components/SourceStamp';
import ReportView from './ReportView';
import { client, ApiClientError } from '../../api/client';
import type { ProfileInput } from '../../api/types';

const REPORT_TIMEOUT_MS = 65_000;

export default function AdvisorPage() {
  const [symbols, setSymbols] = useState<string[]>(['510300', '511010', '518880', '511880']);
  const abortRef = useRef<AbortController | null>(null);

  const mutation = useMutation({
    mutationFn: async (profile: ProfileInput) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const timeoutId = setTimeout(() => controller.abort(), REPORT_TIMEOUT_MS);
      try {
        const res = await client.post<{ content: string; source: string; as_of: string; is_fallback: boolean; warnings: string[] }>(
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
      mutation.mutate(values);
    },
    [mutation],
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
    (mutation.error.code === 'model_unavailable' || mutation.error.code === 'no_api_key');

  return (
    <div>
      <SectionHeader title="Agent 咨询报告" subtitle="填写投资者画像，获取 AI 金融咨询服务" />

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={8}>
          <ProfileForm
            onSubmit={handleSubmit}
            loading={isLoading}
            symbols={symbols}
            onSymbolsChange={setSymbols}
          />
        </Col>

        <Col xs={24} lg={16}>
          {!mutation.isError && !mutation.isSuccess && !mutation.isPending && (
            <Card>
              <Empty description="填写左侧画像表单，点击「生成报告」开始咨询" />
            </Card>
          )}

          {mutation.isPending && (
            <Card>
              <PageState state="loading" />
              <div style={{ textAlign: 'center', marginTop: 8 }}>
                <Tag icon={<ClockCircleOutlined />} color="processing">正在生成报告，请耐心等待（最多60秒）</Tag>
              </div>
            </Card>
          )}

          {isTimeout && (
            <Card>
              <Alert
                type="warning"
                showIcon
                message="报告生成超时"
                description="当前请求超过 60 秒未返回，可能是模型响应较慢或网络异常。请稍后重试。"
                action={
                  <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>
                    重试
                  </Button>
                }
              />
            </Card>
          )}

          {isNoModel && (
            <Card>
              <Alert
                type="info"
                showIcon
                icon={<RobotOutlined />}
                message="Agent 暂不可用"
                description="模型 API Key 未配置或服务暂不可用。您仍可使用行情、风险与配置页面进行参考。"
              />
            </Card>
          )}

          {isApiError && !isNoModel && (
            <Card>
              <Alert
                type="error"
                showIcon
                message="报告生成失败"
                description={mutation.error instanceof ApiClientError ? mutation.error.message : '请求异常，请稍后重试'}
                action={
                  <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>
                    重试
                  </Button>
                }
              />
            </Card>
          )}

          {mutation.isSuccess && (!mutation.data?.data?.content || mutation.data.data.content.trim().length === 0) && (
            <Card>
              <Alert
                type="warning"
                showIcon
                message="报告内容为空"
                description="模型返回了空的咨询报告。"
                action={
                  <Button size="small" icon={<ReloadOutlined />} onClick={handleRetry}>
                    重新生成
                  </Button>
                }
              />
            </Card>
          )}

          {mutation.isSuccess && mutation.data?.data?.content && mutation.data.data.content.trim().length > 0 && (
            <Card>
              <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <SourceStamp
                  source={mutation.data.data.source || 'system'}
                  isFallback={mutation.data.data.is_fallback}
                />
                {mutation.data.data.as_of && (
                  <Tag icon={<ClockCircleOutlined />}>{mutation.data.data.as_of}</Tag>
                )}
              </div>

              <Alert
                type="warning"
                showIcon
                message="风险提示"
                description="本报告由 AI 生成，仅供参考。历史表现不代表未来收益，配置建议不构成投资建议。投资有风险，决策需谨慎。"
                style={{ marginBottom: 16 }}
              />

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
        </Col>
      </Row>
    </div>
  );
}