// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSSEStream } from './useSSE';
import { useChatStore } from '@/stores/chat';

beforeEach(() => {
  localStorage.clear();
  useChatStore.setState({ messages: [], isStreaming: false, abortController: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useSSEStream lifecycle', () => {
  it('marks the assistant complete when the response reaches EOF without metadata', async () => {
    const reader = {
      read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
      cancel: vi.fn().mockResolvedValue(undefined),
      releaseLock: vi.fn(),
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader },
    }));
    const { result } = renderHook(() => useSSEStream());

    await act(async () => {
      await result.current.stream('hello');
    });

    const assistant = useChatStore.getState().messages.find((message) => message.role === 'assistant');
    expect(assistant?.isStreaming).toBe(false);
  });

  it('aborts the active request when the hook unmounts', async () => {
    let signal: AbortSignal | undefined;
    vi.stubGlobal('fetch', vi.fn((_url, init?: RequestInit) => new Promise((_resolve, reject) => {
      signal = init?.signal ?? undefined;
      signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const { result, unmount } = renderHook(() => useSSEStream());

    act(() => {
      void result.current.stream('hello');
    });
    await waitFor(() => expect(signal).toBeDefined());
    unmount();

    await waitFor(() => expect(signal?.aborted).toBe(true));
  });
});
