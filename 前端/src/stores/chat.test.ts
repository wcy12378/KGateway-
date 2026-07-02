import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatStore } from './chat';
import type { ChatMessage } from '@/types';

const assistant: ChatMessage = {
  id: 'assistant-1',
  role: 'assistant',
  content: '',
  timestamp: 1,
  isStreaming: true,
};

beforeEach(() => {
  useChatStore.setState({ messages: [], isStreaming: false, abortController: null });
});

describe('chat store message targeting', () => {
  it('updates an assistant by id even when a system message follows it', () => {
    useChatStore.setState({
      messages: [assistant, { id: 'system-1', role: 'system', content: 'notice', timestamp: 2 }],
    });

    useChatStore.getState().appendAssistantContent('assistant-1', 'answer');

    expect(useChatStore.getState().messages[0].content).toBe('answer');
  });

  it('cancels the active request and clears streaming flags', () => {
    const abort = vi.fn();
    useChatStore.setState({
      messages: [assistant],
      isStreaming: true,
      abortController: { abort } as unknown as AbortController,
    });

    useChatStore.getState().cancelStreaming();

    expect(abort).toHaveBeenCalledOnce();
    expect(useChatStore.getState().isStreaming).toBe(false);
    expect(useChatStore.getState().messages[0].isStreaming).toBe(false);
  });
});
