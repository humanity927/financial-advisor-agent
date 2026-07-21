import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { Eye, MessageSquare, Trash2 } from 'lucide-react';
import { client } from '../../api/client';
import type { ApiResponse, ChatSession, SessionSummary } from '../../api/types';
import SectionHeader from '../../components/SectionHeader';
import ReportView from '../advisor/ReportView';

function localTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [detailId, setDetailId] = useState<string | null>(null);
  const listQuery = useQuery({
    queryKey: ['sessions'],
    queryFn: ({ signal }) => client.get<{ sessions: SessionSummary[] }>('/sessions', signal),
  });
  const detailQuery = useQuery({
    queryKey: ['sessions', detailId],
    queryFn: ({ signal }) => client.get<ChatSession>(`/sessions/${detailId}`, signal),
    enabled: Boolean(detailId),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => client.delete(`/sessions/${id}`),
    onSuccess: (_response, deletedId) => {
      setDetailId(null);
      queryClient.setQueryData<ApiResponse<{ sessions: SessionSummary[] }>>(
        ['sessions'],
        (current) => current
          ? {
              ...current,
              data: {
                sessions: current.data.sessions.filter((item) => item.id !== deletedId),
              },
            }
          : current,
      );
      void queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });
  const clearMutation = useMutation({
    mutationFn: () => client.delete<{ deleted: number }>('/sessions'),
    onSuccess: () => {
      queryClient.setQueryData<ApiResponse<{ sessions: SessionSummary[] }>>(
        ['sessions'],
        (current) => current ? { ...current, data: { sessions: [] } } : current,
      );
      void queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });

  const confirmDelete = (id: string) => {
    Modal.confirm({
      title: '删除这条咨询记录？',
      content: '删除后无法从历史记录恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(id),
    });
  };

  const confirmClear = () => {
    Modal.confirm({
      title: '清空全部历史记录？',
      content: '仅删除 .runtime 中的本地咨询记录，不影响行情缓存。',
      okText: '全部清空',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => clearMutation.mutateAsync(),
    });
  };

  const columns: TableColumnsType<SessionSummary> = [
    { title: '咨询主题', dataIndex: 'title', key: 'title', ellipsis: true },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 180, render: localTime },
    { title: '消息', dataIndex: 'message_count', key: 'message_count', width: 76 },
    {
      title: '画像', dataIndex: 'profile_fields', key: 'profile_fields', width: 100,
      render: (count: number) => <Tag color={count === 7 ? 'success' : 'processing'}>{count}/7</Tag>,
    },
    {
      title: '标的', dataIndex: 'symbols', key: 'symbols', width: 170,
      render: (symbols: string[]) => symbols.length ? symbols.join('、') : '未选择',
    },
    {
      title: '操作', key: 'actions', width: 156, fixed: 'right',
      render: (_, row) => (
        <Space size="small">
          <Button type="text" icon={<Eye size={15} />} aria-label={`查看 ${row.title}`} onClick={() => setDetailId(row.id)} />
          <Button type="text" icon={<MessageSquare size={15} />} aria-label={`继续 ${row.title}`} onClick={() => navigate(`/advisor?session=${row.id}`)} />
          <Button type="text" danger icon={<Trash2 size={15} />} aria-label={`删除 ${row.title}`} onClick={() => confirmDelete(row.id)} />
        </Space>
      ),
    },
  ];

  const sessions = listQuery.data?.data.sessions ?? [];
  const detail = detailQuery.data?.data;

  return (
    <div>
      <SectionHeader
        title="历史记录"
        subtitle="恢复、查看或删除保存在本机 .runtime 的咨询会话"
        actions={<Button danger icon={<Trash2 size={15} />} disabled={sessions.length === 0} loading={clearMutation.isPending} onClick={confirmClear}>清空记录</Button>}
      />
      {listQuery.isError && <Alert type="error" showIcon message="历史记录加载失败" description={listQuery.error instanceof Error ? listQuery.error.message : '请求失败'} />}
      {!listQuery.isLoading && !listQuery.isError && sessions.length === 0 ? (
        <Empty description="暂无咨询记录" />
      ) : (
        <Table
          loading={listQuery.isLoading}
          dataSource={sessions}
          columns={columns}
          rowKey="id"
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 900 }}
          size="middle"
        />
      )}

      <Drawer
        title={detail?.title ?? '会话详情'}
        width={720}
        open={Boolean(detailId)}
        onClose={() => setDetailId(null)}
        extra={detail && <Button type="primary" onClick={() => navigate(`/advisor?session=${detail.id}`)}>继续咨询</Button>}
      >
        {detailQuery.isLoading && <Typography.Text type="secondary">正在读取...</Typography.Text>}
        {detailQuery.isError && <Alert type="error" showIcon message="会话详情加载失败" />}
        {detail && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="创建时间">{localTime(detail.created_at)}</Descriptions.Item>
              <Descriptions.Item label="更新时间">{localTime(detail.updated_at)}</Descriptions.Item>
              <Descriptions.Item label="画像字段">{Object.keys(detail.profile).length}/7</Descriptions.Item>
              <Descriptions.Item label="关注标的">{detail.symbols.join('、') || '无'}</Descriptions.Item>
            </Descriptions>
            {detail.messages.map((item) => (
              <section key={item.id}>
                <Typography.Text strong>{item.role === 'user' ? '用户' : 'Agent'}</Typography.Text>
                <Typography.Text type="secondary"> · {localTime(item.created_at)}</Typography.Text>
                <div style={{ marginTop: 8 }}>
                  {item.role === 'assistant' && item.content.includes('## ')
                    ? <ReportView content={item.content} />
                    : <Typography.Paragraph>{item.content}</Typography.Paragraph>}
                </div>
              </section>
            ))}
          </Space>
        )}
      </Drawer>
    </div>
  );
}
