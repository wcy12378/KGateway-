/**
 * 网关前端契约工具。
 *
 * 本文件集中维护后端接口路径和 SSE 帧解析逻辑。UI 组件应该依赖解析后的
 * 帧和 endpoint helper，而不是直接依赖后端原始 payload 结构。
 */
import type { CacheHitType, CircuitState, ResponseSource, SSEEvent, SSEPhase } from '@/types';
import { apiUrl } from '@/lib/http';

export const GATEWAY_PROTOCOL_VERSION = 'gateway.sse.v1';

export const GATEWAY_ENDPOINTS = {
  stream: apiUrl('/api/v1/gateway/stream'),
  contract: apiUrl('/api/v1/gateway/contract'),
  metrics: apiUrl('/api/v1/monitor/metrics'),
  traces: apiUrl('/api/v1/monitor/traces'),
  circuitBreaker: apiUrl('/api/v1/monitor/circuit-breaker'),
  workflows: apiUrl('/api/v1/gateway/workflows'),
  workflow: apiUrl('/api/v1/gateway/workflow'),
  prompts: apiUrl('/api/v1/gateway/prompts'),
  audit: apiUrl('/api/v1/gateway/audit'),
} as const;

export function auditEndpoint(filters: { limit?: number; offset?: number; tool?: string; resultStatus?: string } = {}): string {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 50), offset: String(filters.offset ?? 0) });
  if (filters.tool) params.set('tool', filters.tool);
  if (filters.resultStatus) params.set('result_status', filters.resultStatus);
  return `${GATEWAY_ENDPOINTS.audit}?${params.toString()}`;
}

export type BreakerAction = 'force-open' | 'force-close';

export function tracesEndpoint(limit = 20, offset = 0): string {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return `${GATEWAY_ENDPOINTS.traces}?${params.toString()}`;
}

export function breakerActionEndpoint(action: BreakerAction): string {
  return `${GATEWAY_ENDPOINTS.circuitBreaker}/${action}`;
}

export function normalizeCircuitState(value: unknown): CircuitState | 'N/A' | undefined {
  const normalized = typeof value === 'string' ? value.trim().toUpperCase() : '';
  if (
    normalized === 'CLOSED' ||
    normalized === 'OPEN' ||
    normalized === 'HALF_OPEN' ||
    normalized === 'N/A'
  ) {
    return normalized;
  }
  return undefined;
}

const PHASES = new Set<SSEPhase>(['checking_cache', 'cache_hit', 'running_fast_lane', 'retrieving_knowledge', 'waiting_provider', 'running_agent']);
const CACHE_HIT_TYPES = new Set<CacheHitType>(['none', 'exact', 'semantic']);
const RESPONSE_SOURCES = new Set<ResponseSource>([
  'cache',
  'calculator',
  'faq',
  'provider',
  'agent',
  'knowledge_unavailable',
]);

export type ParsedSSEFrame =
  | { kind: 'done' }
  | { kind: 'text'; text: string; circuitBreaker?: boolean }
  | { kind: 'metadata'; event: SSEEvent }
  | { kind: 'error'; event: SSEEvent }
  | { kind: 'info'; text: string; phase?: SSEPhase; circuitBreaker?: boolean }
  | { kind: 'unknown' };

export function parseSSEPayload(payload: string): ParsedSSEFrame {
  if (payload === '[DONE]') {
    return { kind: 'done' };
  }

  let data: Record<string, unknown>;
  try {
    data = JSON.parse(payload);
  } catch {
    return {
      kind: 'error',
      event: {
        status: 'error',
        text: '',
        error: 'STREAM_PARSE_ERROR',
      },
    };
  }

  const status = typeof data.status === 'string' ? data.status : '';
  const event = typeof data.event === 'string' ? data.event : status;
  const protocolVersion =
    typeof data.protocol_version === 'string' ? data.protocol_version : undefined;
  const text = typeof data.text === 'string' ? data.text : '';
  const error = typeof data.error === 'string' ? data.error : '';
  const hasCB = data.circuit_breaker === true;

  if (status === 'info' || event === 'info') {
    const phase = typeof data.phase === 'string' && PHASES.has(data.phase as SSEPhase)
      ? data.phase as SSEPhase
      : undefined;
    return { kind: 'info', text, phase, circuitBreaker: hasCB || undefined };
  }

  if (status === 'metadata') {
    return {
      kind: 'metadata',
      event: {
        status: 'metadata',
        event: 'metadata',
        protocol_version: protocolVersion,
        text: '',
        cache_hit: typeof data.cache_hit === 'boolean' ? data.cache_hit : undefined,
        circuit_breaker: hasCB || undefined,
        circuit_breaker_state: normalizeCircuitState(data.circuit_breaker_state),
        trace_id: typeof data.trace_id === 'string' ? data.trace_id : undefined,
        model: typeof data.model === 'string' ? data.model : undefined,
        provider: typeof data.provider === 'string' ? data.provider : undefined,
        routing_decision:
          typeof data.routing_decision === 'string' ? data.routing_decision : undefined,
        agent_iterations:
          typeof data.agent_iterations === 'number' ? data.agent_iterations : undefined,
        agent_steps:
          typeof data.agent_steps === 'number' ? data.agent_steps : undefined,
        total_tokens: typeof data.total_tokens === 'number' ? data.total_tokens : undefined,
        estimated_cost_usd:
          typeof data.estimated_cost_usd === 'number' ? data.estimated_cost_usd : undefined,
        ttft_ms: typeof data.ttft_ms === 'number' ? data.ttft_ms : undefined,
        provider_ttft_ms:
          typeof data.provider_ttft_ms === 'number' ? data.provider_ttft_ms : undefined,
        cache_lookup_ms:
          typeof data.cache_lookup_ms === 'number' ? data.cache_lookup_ms : undefined,
        app_overhead_ms:
          typeof data.app_overhead_ms === 'number' ? data.app_overhead_ms : undefined,
        total_latency_ms:
          typeof data.total_latency_ms === 'number' ? data.total_latency_ms : undefined,
        session_id: typeof data.session_id === 'string' ? data.session_id : undefined,
        cache_hit_type: typeof data.cache_hit_type === 'string' && CACHE_HIT_TYPES.has(data.cache_hit_type as CacheHitType)
          ? data.cache_hit_type as CacheHitType
          : undefined,
        response_source: typeof data.response_source === 'string' && RESPONSE_SOURCES.has(data.response_source as ResponseSource)
          ? data.response_source as ResponseSource
          : undefined,
      },
    };
  }

  if (status === 'error' || error) {
    return {
      kind: 'error',
      event: {
        status: 'error',
        event: 'error',
        protocol_version: protocolVersion,
        text: '',
        cache_hit: typeof data.cache_hit === 'boolean' ? data.cache_hit : undefined,
        circuit_breaker: hasCB || undefined,
        circuit_breaker_state: normalizeCircuitState(data.circuit_breaker_state),
        trace_id: typeof data.trace_id === 'string' ? data.trace_id : undefined,
        model: typeof data.model === 'string' ? data.model : undefined,
        session_id: typeof data.session_id === 'string' ? data.session_id : undefined,
        error: error || 'Unknown error',
      },
    };
  }

  if (text && status !== 'metadata' && status !== 'error') {
    return hasCB
      ? { kind: 'info', text, circuitBreaker: true }
      : { kind: 'text', text, circuitBreaker: undefined };
  }

  return { kind: 'unknown' };
}
