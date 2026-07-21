import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiClientError, client } from '../api/client';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('API client error mapping', () => {
  it('preserves structured backend error codes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({
          ok: false,
          data: null,
          meta: {
            source: 'system',
            as_of: '2026-07-20T00:00:00+08:00',
            request_id: 'test-request',
            is_fallback: false,
          },
          warnings: [],
          error: {
            code: 'no_api_key',
            message: '模型 API Key 未配置',
            retryable: false,
          },
        }),
      }),
    );

    const request = client.get('/advisor/report');
    await expect(request).rejects.toBeInstanceOf(ApiClientError);
    await expect(request).rejects.toMatchObject({
      code: 'no_api_key',
      message: '模型 API Key 未配置',
      retryable: false,
    });
  });
});
