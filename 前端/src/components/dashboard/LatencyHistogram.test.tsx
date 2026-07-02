// @vitest-environment jsdom
import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LatencyHistogram } from './LatencyHistogram';

describe('LatencyHistogram layout', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not emit a negative-size ResponsiveContainer warning', () => {
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    render(<LatencyHistogram distribution={null} />);

    expect(warning.mock.calls.flat().join(' ')).not.toContain('width(-1)');
  });
});
