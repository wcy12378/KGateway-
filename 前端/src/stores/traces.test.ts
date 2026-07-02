import { beforeEach, describe, expect, it } from 'vitest';
import { useTracesStore } from './traces';

beforeEach(() => {
  useTracesStore.setState({ offset: 40 });
});

describe('trace filters', () => {
  it('returns to the first page when filters change', () => {
    useTracesStore.getState().setFilters({ traceIdSearch: 'trace-1' });
    expect(useTracesStore.getState().offset).toBe(0);
  });
});
