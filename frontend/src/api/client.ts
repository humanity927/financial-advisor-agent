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
    // Try to parse error body, fallback to generic
    try {
      const err = (await res.json()) as ApiResponse<unknown>;
      if (!err.ok && err.error) {
        throw new ApiClientError(err.error.code, err.error.message, err.error.retryable);
      }
    } catch {
      // ignore parse failure
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
};

export { client, ApiClientError };