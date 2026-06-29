/**
 * 前端共享类型定义。
 *
 * 本文件负责定义网关请求、SSE 事件、监控指标、trace 和聊天消息类型。它不
 * 负责运行时校验、接口请求或 UI 渲染。
 */
// ===== 枚举 =====
export type Department = 'legal' | 'hr' | 'engineering' | 'finance' | 'general';
export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';
export type SSEStatus = 'text' | 'info' | 'metadata' | 'error';

// ===== 请求/响应类型 =====
export interface GatewayRequest {
  user_id: string;
  tenant_id: string;
  department: Department;
  question: string;
  session_id?: string;
  advanced_reasoning?: boolean;
}

export interface SSEEvent {
  status: SSEStatus;
  event?: SSEStatus;
  protocol_version?: string;
  text: string;
  cache_hit?: boolean;
  trace_id?: string;
  model?: string;
  circuit_breaker?: boolean;
  circuit_breaker_state?: CircuitState | 'N/A';
  routing_decision?: string;
  agent_iterations?: number;
  agent_steps?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  ttft_ms?: number;
  total_latency_ms?: number;
  session_id?: string;
  error?: string;
}

export interface MetricsSnapshot {
  total_requests: number;
  cache_hit_rate: number;
  cache_hits: number;
  cache_misses: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  latency_distribution: LatencyDistribution;
}

export interface LatencyDistribution {
  under_100ms: number;
  '100_500ms': number;
  '500ms_1s': number;
  '1s_5s': number;
  over_5s: number;
}

export interface CircuitBreakerStats {
  name: string;
  state: CircuitState;
  failure_count: number;
  failure_threshold: number;
  recovery_timeout: number;
  total_requests: number;
  total_failures: number;
  total_rejected: number;
}

export interface TraceSpan {
  name: string;
  duration_ms: number;
  result?: string;
}

export interface TraceRecord {
  trace_id: string;
  timestamp: string;
  cache_hit: boolean;
  model: string;
  total_tokens: number;
  estimated_cost_usd: number;
  ttft_ms: number;
  total_latency_ms: number;
  circuit_breaker: boolean;
  routing_decision: string;
  agent_iterations: number;
  user_id: string;
  department: Department;
  spans: TraceSpan[];
}

export interface TraceListResponse {
  traces: TraceRecord[];
  total: number;
  limit: number;
  offset: number;
}

// ===== 前端内部类型 =====
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata?: SSEEvent;
  timestamp: number;
  isStreaming?: boolean;
}
