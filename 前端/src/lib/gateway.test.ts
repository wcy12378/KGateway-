import { describe, expect, it } from 'vitest';
import { GATEWAY_ENDPOINTS, normalizeCircuitState, parseSSEPayload } from './gateway';

describe('gateway contract', () => {
  it('uses the monitoring endpoint for metrics', () => {
    expect(GATEWAY_ENDPOINTS.metrics).toBe('/api/v1/monitor/metrics');
  });

  it('preserves the knowledge unavailable response source', () => {
    const frame = parseSSEPayload(JSON.stringify({
      status: 'metadata',
      event: 'metadata',
      text: '',
      response_source: 'knowledge_unavailable',
    }));

    expect(frame.kind).toBe('metadata');
    if (frame.kind === 'metadata') {
      expect(frame.event.response_source).toBe('knowledge_unavailable');
    }
  });

  it('normalizes lowercase circuit breaker states from the backend', () => {
    expect(normalizeCircuitState('closed')).toBe('CLOSED');
    expect(normalizeCircuitState('half_open')).toBe('HALF_OPEN');
    expect(normalizeCircuitState('unexpected')).toBeUndefined();
  });
});
