/**
 * 前端统一 HTTP 请求层。
 *
 * 本文件负责 API 地址拼接、错误响应解析、超时和 JSON 解码。页面组件只关心
 * 业务数据与可展示的错误消息，不再重复处理 response.ok。
 */
const DEFAULT_TIMEOUT_MS = 15_000;
const TOKEN_STORAGE_KEY = 'kagent_token';
const DEV_AUTH_ENABLED = import.meta.env.VITE_ENABLE_DEV_AUTH === 'true';
let pendingTokenRequest: Promise<string | null> | null = null;

export class HttpError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

function normalizeBaseUrl(value: string | undefined): string {
  return (value ?? '').trim().replace(/\/+$/, '');
}

export const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_BASE);

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `请求失败（HTTP ${response.status}）`;
  const contentType = response.headers.get('content-type') ?? '';

  try {
    if (contentType.includes('application/json')) {
      const body = (await response.json()) as Record<string, unknown>;
      for (const key of ['detail', 'error', 'message']) {
        const value = body[key];
        if (typeof value === 'string' && value.trim()) return value;
      }
      return fallback;
    }

    const text = (await response.text()).trim();
    return text || fallback;
  } catch {
    return fallback;
  }
}

interface RequestJsonOptions extends RequestInit {
  timeoutMs?: number;
}

interface TokenResponse {
  access_token: string;
}

function storedToken(): string | null {
  return typeof window === 'undefined'
    ? null
    : window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export async function ensureToken(): Promise<string | null> {
  const existing = storedToken();
  if (existing) return existing;
  if (typeof window === 'undefined') return null;
  if (!DEV_AUTH_ENABLED) return null;
  if (pendingTokenRequest) return pendingTokenRequest;

  pendingTokenRequest = (async () => {
    try {
      const response = await fetch(apiUrl('/api/v1/auth/token'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'default_user',
          tenant_id: 'default_tenant',
          department: 'general',
        }),
      });
      if (!response.ok) throw new HttpError(await readErrorMessage(response), response.status);
      const data = (await response.json()) as TokenResponse;
      window.localStorage.setItem(TOKEN_STORAGE_KEY, data.access_token);
      return data.access_token;
    } catch (error) {
      console.warn('Token 获取失败，降级为无认证模式', error);
      return null;
    } finally {
      pendingTokenRequest = null;
    }
  })();
  return pendingTokenRequest;
}

export async function createAuthHeaders(initial?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initial);
  const token = await ensureToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return headers;
}

export async function requestJson<T>(
  path: string,
  options: RequestJsonOptions = {}
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...requestOptions } = options;
  const timeoutController = new AbortController();
  const timeoutId = window.setTimeout(() => timeoutController.abort(), timeoutMs);
  const abortFromCaller = () => timeoutController.abort();
  signal?.addEventListener('abort', abortFromCaller, { once: true });

  try {
    const headers = await createAuthHeaders(requestOptions.headers);
    const response = await fetch(apiUrl(path), {
      ...requestOptions,
      headers,
      signal: timeoutController.signal,
    });
    if (!response.ok) {
      throw new HttpError(await readErrorMessage(response), response.status);
    }
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text.trim()) return undefined as T;
    return JSON.parse(text) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      if (signal?.aborted) throw error;
      throw new Error('请求超时，请检查网关服务后重试。', { cause: error });
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
