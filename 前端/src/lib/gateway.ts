/**
 * 网关前端契约工具。
 *
 * 本文件集中维护后端接口路径和 SSE 帧解析逻辑。UI 组件应该依赖解析后的
 * 帧和 endpoint helper，而不是直接依赖后端原始 payload 结构。
 */
import type { CircuitState, SSEEvent } from '@/types';
import { apiUrl } from '@/lib/http';

export const GATEWAY_PROTOCOL_VERSION = 'gateway.sse.v1';

export const GATEWAY_ENDPOINTS = {
  stream: apiUrl('/api/v1/gateway/stream'),
  contract: apiUrl('/api/v1/gateway/contract'),
  metrics: apiUrl('/api/v1/gateway/metrics'),
  traces: apiUrl('/api/v1/monitor/traces'),
  circuitBreaker: apiUrl('/api/v1/monitor/circuit-breaker'),
} as const;

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

function parseCircuitState(value: unknown): CircuitState | 'N/A' | undefined {
  if (
    value === 'CLOSED' ||
    value === 'OPEN' ||
    value === 'HALF_OPEN' ||
    value === 'N/A'
  ) {
    return value;
  }
  return undefined;
}

export type ParsedSSEFrame =
  | { kind: 'done' }
  | { kind: 'text'; text: string; circuitBreaker?: boolean }
  | { kind: 'metadata'; event: SSEEvent }
  | { kind: 'error'; event: SSEEvent }
  | { kind: 'info'; text: string; circuitBreaker?: boolean }
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
    return { kind: 'info', text, circuitBreaker: hasCB || undefined };
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
        circuit_breaker_state: parseCircuitState(data.circuit_breaker_state),
        trace_id: typeof data.trace_id === 'string' ? data.trace_id : undefined,
        model: typeof data.model === 'string' ? data.model : undefined,
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
        total_latency_ms:
          typeof data.total_latency_ms === 'number' ? data.total_latency_ms : undefined,
        session_id: typeof data.session_id === 'string' ? data.session_id : undefined,
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
        circuit_breaker_state: parseCircuitState(data.circuit_breaker_state),
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
