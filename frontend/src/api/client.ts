import type { ApiResponse } from './types';

const BASE_URL = '/api';

class ApiClientError extends Error {
  code: string;
  retryable: boolean;

  constructor(code: string, message: string, retryable: boolean) {
    super(message);
    this.name = 'ApiClientError';
    this.code = code;
    this.retryable = retryable;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<ApiResponse<T>> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!res.ok) {
    let parsed: ApiResponse<unknown> | null = null;
    try {
      parsed = (await res.json()) as ApiResponse<unknown>;
    } catch {
      // The response may not contain JSON; use the stable HTTP fallback below.
    }
    if (parsed && !parsed.ok && parsed.error) {
      throw new ApiClientError(parsed.error.code, parsed.error.message, parsed.error.retryable);
    }
    throw new ApiClientError(
      'http_error',
      `服务器响应异常 (${res.status})`,
      res.status >= 500,
    );
  }

  return res.json() as Promise<ApiResponse<T>>;
}

const client = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>('GET', path, undefined, signal),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('POST', path, body, signal),
  delete: <T>(path: string, signal?: AbortSignal) =>
    request<T>('DELETE', path, undefined, signal),
};

export { client, ApiClientError };
