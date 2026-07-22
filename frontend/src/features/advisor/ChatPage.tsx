import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircle2,
  Clock3,
  History,
  MessageSquarePlus,
  RefreshCw,
  Send,
  Square,
  XCircle,
} from 'lucide-react';
import { client, ApiClientError } from '../../api/client';
import type {
  ApiResponse,
  AdvisorRunStatus,
  ChatMessage,
  ChatSession,
  ChatTurnData,
  UiAction,
} from '../../api/types';
import { useWorkspace } from '../../app/WorkspaceContext';
import SectionHeader from '../../components/SectionHeader';
import SourceStamp from '../../components/SourceStamp';
import ReportView from './ReportView';
import './ChatPage.css';

const TOOL_LABELS: Record<string, string> = {
  assess_investor_profile: '用户画像',
  get_market_snapshot: '行情快照',
  analyze_asset_risk: '风险指标',
  build_allocation: '配置建议',
};

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function MessageItem({ item }: { item: ChatMessage }) {
  const isAssistant = item.role === 'assistant';
  return (
    <article className={`chat-message chat-message-${item.role}`}>
      <div className="chat-message-meta">
        <strong>{isAssistant ? 'Agent' : '你'}</strong>
        <span>{formatTime(item.created_at)}</span>
        {item.status === 'error' && <Tag color="error">失败</Tag>}
        {item.status === 'cancelled' && <Tag color="warning">已终止</Tag>}
        {item.context_status === 'historical' && <Tag>历史上下文</Tag>}
      </div>
      <div className="chat-message-body">
        {isAssistant && item.content.includes('## ') ? (
          <ReportView content={item.content} />
        ) : (
          <Typography.Paragraph>{item.content}</Typography.Paragraph>
        )}
      </div>
      {isAssistant && item.tool_calls.length > 0 && (
        <div className="chat-tool-calls">
          {item.tool_calls.map((call) => (
            <Tag
              key={`${call.tool}-${call.called_at}`}
              icon={call.ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
              color={call.ok ? 'success' : 'error'}
            >
              {TOOL_LABELS[call.tool] ?? call.tool} · {call.source}
              {call.is_fallback ? ' · 回退' : ''}
            </Tag>
          ))}
        </div>
      )}
      {isAssistant && item.as_of && (
        <div className="chat-source-row">
          <SourceStamp source={item.source} isFallback={item.is_fallback} />
          <span>{item.context_status === 'historical' ? '历史数据截至' : '数据截至'} {item.as_of}</span>
        </div>
      )}
    </article>
  );
}

export default function ChatPage() {
  const workspace = useWorkspace();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [session, setSession] = useState<ChatSession | null>(null);
  const [input, setInput] = useState('');
  const [requestId, setRequestId] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const createRequestedRef = useRef(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const hydratedSessionRef = useRef<string | null>(null);
  const [messageApi, messageContext] = message.useMessage();
  const sessionId = searchParams.get('session');

  const sessionQuery = useQuery({
    queryKey: ['sessions', sessionId],
    queryFn: ({ signal }) => client.get<ChatSession>(`/sessions/${sessionId}`, signal),
    enabled: Boolean(sessionId),
    retry: false,
  });

  const runStatusQuery = useQuery({
    queryKey: ['advisor-run', requestId],
    queryFn: ({ signal }) => client.get<AdvisorRunStatus>(`/advisor/runs/${requestId}`, signal),
    enabled: Boolean(requestId),
    refetchInterval: requestId ? 700 : false,
    retry: false,
  });

  useEffect(() => {
    const restored = sessionQuery.data?.data;
    if (!restored) return;
    setSession((current) => {
      if (!current || current.id !== restored.id) return restored;
      if (restored.updated_at < current.updated_at) return current;
      if (
        restored.updated_at === current.updated_at
        && restored.messages.length < current.messages.length
      ) return current;
      return restored;
    });
  }, [sessionQuery.data]);

  useEffect(() => {
    const restored = sessionQuery.data?.data;
    if (!restored) return;
    if (hydratedSessionRef.current === restored.id) return;
    hydratedSessionRef.current = restored.id;

    const actions: UiAction[] = [];
    if (Object.keys(restored.profile).length > 0) {
      actions.push({ type: 'profile.patch', payload: restored.profile });
    }
    for (const symbol of restored.symbols) {
      actions.push({ type: 'market.symbol.add', payload: { symbol } });
    }
    if (restored.risk_symbol) {
      actions.push({ type: 'risk.symbol.select', payload: { symbol: restored.risk_symbol } });
    }
    if (restored.current_allocation_pct) {
      actions.push({
        type: 'portfolio.inputs.patch',
        payload: { current_allocation_pct: restored.current_allocation_pct },
      });
    }
    if (actions.length > 0) {
      void workspace.applyActions(actions).then(setActionFeedback);
    }
  }, [sessionQuery.data, workspace]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [session?.messages.length]);

  const createMutation = useMutation({
    mutationFn: () => client.post<ChatSession>('/sessions', { title: '新咨询' }),
    onSuccess: (response) => {
      setSession(response.data);
      queryClient.setQueryData(['sessions', response.data.id], response);
      setSearchParams({ session: response.data.id }, { replace: true });
      void queryClient.invalidateQueries({ queryKey: ['sessions'], exact: true });
    },
  });

  useEffect(() => {
    if (!sessionId && !session && !createRequestedRef.current) {
      createRequestedRef.current = true;
      createMutation.mutate();
    }
  }, [createMutation, session, sessionId]);

  const applyTurn = useCallback((turn: ChatTurnData, response: ApiResponse<ChatTurnData>) => {
    setSession(turn.session);
    queryClient.setQueryData<ApiResponse<ChatSession>>(
      ['sessions', turn.session.id],
      { ...response, data: turn.session },
    );
    void queryClient.invalidateQueries({ queryKey: ['sessions'], exact: true });
    void workspace.applyActions(turn.actions).then(setActionFeedback);
  }, [queryClient, workspace]);

  const sendMutation = useMutation({
    mutationFn: async (content: string) => {
      if (!session) throw new Error('会话尚未创建');
      const nextRequestId = crypto.randomUUID();
      setRequestId(nextRequestId);
      const controller = new AbortController();
      abortRef.current = controller;
      return client.post<ChatTurnData>(
        `/sessions/${session.id}/messages`,
        { content, client_request_id: nextRequestId },
        controller.signal,
      );
    },
    onSuccess: (response) => {
      applyTurn(response.data, response);
      setInput('');
    },
    onError: () => {
      if (sessionId) void sessionQuery.refetch();
    },
    onSettled: () => {
      abortRef.current = null;
      setRequestId(null);
    },
  });

  const regenerateMutation = useMutation({
    mutationFn: () => {
      if (!session) throw new Error('会话尚未创建');
      const nextRequestId = crypto.randomUUID();
      setRequestId(nextRequestId);
      const controller = new AbortController();
      abortRef.current = controller;
      return client.post<ChatTurnData>(
        `/sessions/${session.id}/regenerate`,
        { client_request_id: nextRequestId },
        controller.signal,
      );
    },
    onSuccess: (response) => applyTurn(response.data, response),
    onError: () => {
      if (sessionId) void sessionQuery.refetch();
    },
    onSettled: () => {
      abortRef.current = null;
      setRequestId(null);
    },
  });

  const handleSend = () => {
    const content = input.trim();
    if (content && !sendMutation.isPending) sendMutation.mutate(content);
  };

  const handleStop = async () => {
    if (requestId) {
      try {
        await client.post(`/advisor/runs/${requestId}/cancel`);
      } catch {
        messageApi.warning('终止请求未得到服务端确认');
      }
    }
    abortRef.current?.abort();
  };

  const handleNew = () => {
    createRequestedRef.current = false;
    setSession(null);
    setInput('');
    setActionFeedback([]);
    setSearchParams({}, { replace: true });
  };

  const isGenerating = sendMutation.isPending || regenerateMutation.isPending;
  const activeToolCalls = runStatusQuery.data?.data.tool_calls ?? [];
  const error = sendMutation.error ?? regenerateMutation.error ?? sessionQuery.error;
  const errorMessage = error instanceof ApiClientError
    ? error.message
    : error instanceof DOMException && error.name === 'AbortError'
      ? '本次生成已终止'
      : error instanceof Error
        ? error.message
        : null;

  return (
    <div className="chat-page">
      {messageContext}
      <SectionHeader
        title="Agent 咨询"
        subtitle="Hermes 结合会话上下文，按需调用确定性金融工具"
        actions={
          <Space wrap>
            <Button icon={<History size={15} />} onClick={() => navigate('/history')}>历史记录</Button>
            <Button icon={<MessageSquarePlus size={15} />} onClick={handleNew}>新建咨询</Button>
          </Space>
        }
      />

      <div className="chat-workspace">
        <section className="chat-thread" aria-label="咨询消息流">
          {(!session && createMutation.isPending) || sessionQuery.isLoading ? (
            <div className="chat-centered"><Spin /></div>
          ) : sessionQuery.isError ? (
            <Alert type="error" showIcon message="会话恢复失败" description={errorMessage} />
          ) : !session || session.messages.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="开始一段金融咨询"
            />
          ) : (
            session.messages.map((item) => <MessageItem item={item} key={item.id} />)
          )}

          {isGenerating && (
            <article className="chat-message chat-message-assistant chat-pending">
              <div className="chat-message-meta"><strong>Agent</strong><Tag color="processing">处理中</Tag></div>
              <div className="chat-pending-tools">
                {activeToolCalls.length === 0 ? (
                  <span><Clock3 size={14} />正在理解上下文并选择必要工具</span>
                ) : activeToolCalls.map((call) => (
                  <span key={`${call.tool}-${call.called_at}`}>
                    {call.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                    {TOOL_LABELS[call.tool] ?? call.tool} · {call.source}
                  </span>
                ))}
              </div>
            </article>
          )}
          <div ref={endRef} />
        </section>

        <aside className="chat-context" aria-label="咨询上下文">
          <Card size="small" title="已收集画像">
            <div className="chat-profile-grid">
              {Object.entries(workspace.profile).map(([key, value]) => (
                <span key={key}><small>{key}</small><strong>{String(value)}</strong></span>
              ))}
              {Object.keys(workspace.profile).length === 0 && <Typography.Text type="secondary">等待从对话提取</Typography.Text>}
            </div>
          </Card>
          <Card size="small" title="关联标的">
            <Space wrap>{workspace.watchedSymbols.map((item) => <Tag key={item.symbol}>{item.symbol} · {item.name}</Tag>)}</Space>
          </Card>
          {actionFeedback.length > 0 && (
            <Alert type="info" showIcon message="工作台状态更新" description={actionFeedback.join('；')} />
          )}
        </aside>
      </div>

      <div className="chat-composer">
        {errorMessage && (
          <Alert
            type={errorMessage.includes('终止') ? 'warning' : 'error'}
            showIcon
            message={errorMessage}
          />
        )}
        <div className="chat-composer-toolbar">
          <Button
            size="small"
            icon={<RefreshCw size={14} />}
            loading={regenerateMutation.isPending}
            disabled={isGenerating || !session?.messages.some((item) => item.role === 'user')}
            onClick={() => regenerateMutation.mutate()}
          >
            重新生成
          </Button>
        </div>
        <div className="chat-composer-row">
          <Input.TextArea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault();
                handleSend();
              }
            }}
            autoSize={{ minRows: 2, maxRows: 6 }}
            maxLength={4000}
            placeholder="输入咨询内容"
            disabled={!session || isGenerating}
          />
          {isGenerating ? (
            <Button danger icon={<Square size={15} />} onClick={() => void handleStop()}>终止</Button>
          ) : (
            <Button type="primary" icon={<Send size={15} />} onClick={handleSend} disabled={!session || !input.trim()}>发送</Button>
          )}
        </div>
      </div>
    </div>
  );
}
