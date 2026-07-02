export interface LatestRequest {
  signal: AbortSignal;
  isCurrent: () => boolean;
}

export interface LatestRequestController {
  next: () => LatestRequest;
  abort: () => void;
}

export function createLatestRequestController(): LatestRequestController {
  let current: AbortController | null = null;
  return {
    next: () => {
      current?.abort();
      const controller = new AbortController();
      current = controller;
      return {
        signal: controller.signal,
        isCurrent: () => current === controller && !controller.signal.aborted,
      };
    },
    abort: () => {
      current?.abort();
      current = null;
    },
  };
}
