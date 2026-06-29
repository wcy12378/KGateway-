/**
 * 聊天 SSE 流式 Hook。
 *
 * 本文件负责连接网关 stream 接口，并把解析后的帧写入聊天状态。它不负责定义
 * SSE 协议格式、渲染消息 UI 或维护请求参数。
 */
import { useCallback, useEffect } from 'react';
import { GATEWAY_ENDPOINTS, parseSSEPayload } from '@/lib/gateway';
import { createAuthHeaders, readErrorMessage } from '@/lib/http';
import { useChatStore } from '@/stores/chat';
import type { ChatMessage } from '@/types';

/**
 * SSE streaming hook. Transport details stay behind the gateway contract,
 * while this hook only maps parsed frames into chat store state.
 */
export function useSSEStream() {
  const addMessage = useChatStore((s) => s.addMessage);
  const updateLastAssistant = useChatStore((s) => s.updateLastAssistant);
  const setLastMessageMetadata = useChatStore((s) => s.setLastMessageMetadata);
  const setLastMessageStreaming = useChatStore((s) => s.setLastMessageStreaming);
  const setStreaming = useChatStore((s) => s.setStreaming);
  const setAbortController = useChatStore((s) => s.setAbortController);
  const buildRequest = useChatStore((s) => s.buildRequest);

  const stream = useCallback(
    async (text: string) => {
      const controller = new AbortController();
      setAbortController(controller);
      setStreaming(true);

      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      addMessage(userMsg);

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
      };
      addMessage(assistantMsg);

      try {
        const request = buildRequest(text);
        const headers = await createAuthHeaders({ 'Content-Type': 'application/json' });
        const response = await fetch(GATEWAY_ENDPOINTS.stream, {
          method: 'POST',
          headers,
          body: JSON.stringify(request),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(await readErrorMessage(response));
        }

        if (!response.body) {
          throw new Error('Empty streaming response');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;

            const payload = trimmed.slice(6);
            const frame = parseSSEPayload(payload);

            try {
              if (frame.kind === 'done') {
                setLastMessageStreaming(false);
                continue;
              }

              if (frame.kind === 'text' || frame.kind === 'info') {
                updateLastAssistant(frame.text);
                continue;
              }

              if (frame.kind === 'metadata') {
                setLastMessageMetadata(frame.event);
                continue;
              }

              if (frame.kind === 'error') {
                setLastMessageMetadata(frame.event);
                addMessage({
                  id: crypto.randomUUID(),
                  role: 'system',
                  content: frame.event.circuit_breaker
                    ? '请求被熔断器拒绝，请稍后重试或联系管理员。'
                    : frame.event.error || 'Unknown error',
                  timestamp: Date.now(),
                  metadata: frame.event,
                });
              }
            } catch (innerErr) {
              updateLastAssistant('STREAM PARSE ERROR');
              setLastMessageStreaming(false);
              console.error('[useSSE] frame processing error:', innerErr, payload);
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setLastMessageStreaming(false);
        } else {
          addMessage({
            id: crypto.randomUUID(),
            role: 'system',
            content: err instanceof Error ? err.message : 'Connection failed',
            timestamp: Date.now(),
          });
          setLastMessageStreaming(false);
        }
      } finally {
        setStreaming(false);
        setAbortController(null);
      }
    },
    [
      addMessage,
      buildRequest,
      setAbortController,
      setLastMessageMetadata,
      setLastMessageStreaming,
      setStreaming,
      updateLastAssistant,
    ]
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.text) stream(detail.text);
    };
    window.addEventListener('chat:send', handler);
    return () => window.removeEventListener('chat:send', handler);
  }, [stream]);

  return { stream };
}
