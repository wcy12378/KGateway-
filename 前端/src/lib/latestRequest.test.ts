import { describe, expect, it } from 'vitest';
import { createLatestRequestController } from './latestRequest';

describe('latest request controller', () => {
  it('aborts the previous request when a new request starts', () => {
    const controller = createLatestRequestController();
    const first = controller.next();
    const second = controller.next();

    expect(first.signal.aborted).toBe(true);
    expect(first.isCurrent()).toBe(false);
    expect(second.signal.aborted).toBe(false);
    expect(second.isCurrent()).toBe(true);
  });

  it('invalidates the current request when aborted', () => {
    const controller = createLatestRequestController();
    const request = controller.next();
    controller.abort();

    expect(request.signal.aborted).toBe(true);
    expect(request.isCurrent()).toBe(false);
  });
});
