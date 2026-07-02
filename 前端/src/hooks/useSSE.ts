/**
 * 聊天 SSE 流式 Hook。
 *
 * 本文件负责连接网关 stream 接口，并把解析后的帧写入聊天状态。它不负责定义
 * SSE 协议格式、渲染消息 UI 或维护请求参数。
 */
import { useCallback, useEffect, useRef } from 'react';
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
  const appendAssistantContent = useChatStore((s) => s.appendAssistantContent);
  const setMessageMetadata = useChatStore((s) => s.setMessageMetadata);
  const setMessageStreaming = useChatStore((s) => s.setMessageStreaming);
  const setMessagePhase = useChatStore((s) => s.setMessagePhase);
  const setStreaming = useChatStore((s) => s.setStreaming);
  const setAbortController = useChatStore((s) => s.setAbortController);
  const buildRequest = useChatStore((s) => s.buildRequest);
  const controllerRef = useRef<AbortController | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  const stream = useCallback(
    async (text: string) => {
      const controller = new AbortController();
      controllerRef.current?.abort();
      controllerRef.current = controller;
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
      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

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

        reader = response.body.getReader();
        readerRef.current = reader;
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
                setMessageStreaming(assistantMsg.id, false);
                setMessagePhase(assistantMsg.id, undefined);
                continue;
              }

              if (frame.kind === 'text') {
                appendAssistantContent(assistantMsg.id, frame.text);
                continue;
              }

              if (frame.kind === 'info') {
                setMessagePhase(assistantMsg.id, frame.phase);
                continue;
              }

              if (frame.kind === 'metadata') {
                setMessageMetadata(assistantMsg.id, frame.event);
                continue;
              }

              if (frame.kind === 'error') {
                setMessageMetadata(assistantMsg.id, frame.event);
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
              appendAssistantContent(assistantMsg.id, 'STREAM PARSE ERROR');
              setMessageStreaming(assistantMsg.id, false);
              console.error('[useSSE] frame processing error:', innerErr, payload);
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setMessageStreaming(assistantMsg.id, false);
        } else {
          addMessage({
            id: crypto.randomUUID(),
            role: 'system',
            content: err instanceof Error ? err.message : 'Connection failed',
            timestamp: Date.now(),
          });
          setMessageStreaming(assistantMsg.id, false);
        }
      } finally {
        setMessageStreaming(assistantMsg.id, false);
        if (reader && readerRef.current === reader) {
          try {
            reader.releaseLock();
          } catch {
            // Reader may already be released after cancellation.
          }
          readerRef.current = null;
        }
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setStreaming(false);
          setAbortController(null);
        }
      }
    },
    [
      addMessage,
      buildRequest,
      setAbortController,
      appendAssistantContent,
      setMessageMetadata,
      setMessagePhase,
      setMessageStreaming,
      setStreaming,
    ]
  );

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.text) stream(detail.text);
    };
    window.addEventListener('chat:send', handler);
    return () => {
      window.removeEventListener('chat:send', handler);
      controllerRef.current?.abort();
      if (readerRef.current) {
        void readerRef.current.cancel().catch(() => undefined);
      }
    };
  }, [stream]);

  return { stream };
}
