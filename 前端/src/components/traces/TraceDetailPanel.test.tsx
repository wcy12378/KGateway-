// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TraceDetailPanel } from './TraceDetailPanel';
import type { TraceRecord } from '@/types';

const trace: TraceRecord = {
  trace_id: 'trace-1',
  timestamp: '2026-07-02T00:00:00Z',
  cache_hit: false,
  model: 'deepseek-chat',
  total_tokens: 10,
  estimated_cost_usd: 0.01,
  ttft_ms: 100,
  total_latency_ms: 300,
  circuit_breaker: false,
  routing_decision: 'direct',
  agent_iterations: 0,
  user_id: 'user-1',
  department: 'general',
  spans: [
    { name: 'embedding', duration_ms: 10 },
    { name: 'rag_retrieval', duration_ms: 20 },
    { name: 'provider_stream', duration_ms: 200 },
  ],
};

describe('TraceDetailPanel span contract', () => {
  it('renders current backend span names with Chinese labels', () => {
    render(<TraceDetailPanel trace={trace} />);

    expect(screen.getByText('向量生成')).toBeTruthy();
    expect(screen.getByText('RAG 检索')).toBeTruthy();
    expect(screen.getByText('Provider 流式响应')).toBeTruthy();
  });
});
