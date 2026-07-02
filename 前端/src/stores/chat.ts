/**
 * 聊天状态仓库。
 *
 * 本文件负责保存消息列表、流式状态、请求参数和请求构造逻辑。它不负责渲染 UI、
 * 连接 SSE 或定义后端协议。
 */
import { create } from 'zustand';
import type { ChatMessage, GatewayRequest, Department } from '@/types';

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  currentSessionId: string;
  gatewayParams: {
    user_id: string;
    tenant_id: string;
    department: Department;
    advanced_reasoning: boolean;
  };
  abortController: AbortController | null;
}

interface ChatActions {
  addMessage: (msg: ChatMessage) => void;
  appendAssistantContent: (id: string, content: string) => void;
  setMessageMetadata: (id: string, metadata: ChatMessage['metadata']) => void;
  setMessageStreaming: (id: string, streaming: boolean) => void;
  setMessagePhase: (id: string, phase: ChatMessage['phase']) => void;
  setStreaming: (v: boolean) => void;
  setSessionId: (id: string) => void;
  setGatewayParams: (params: Partial<ChatState['gatewayParams']>) => void;
  setAbortController: (ctrl: AbortController | null) => void;
  cancelStreaming: () => void;
  clearMessages: () => void;
  buildRequest: (question: string) => GatewayRequest;
}

export const useChatStore = create<ChatState & ChatActions>((set, get) => ({
  messages: [],
  isStreaming: false,
  currentSessionId: crypto.randomUUID(),
  gatewayParams: {
    user_id: 'default_user',
    tenant_id: 'default_tenant',
    department: 'general',
    advanced_reasoning: false,
  },
  abortController: null,

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),

  appendAssistantContent: (id, content) =>
    set((s) => {
      const messages = s.messages.map((message) =>
        message.id === id && message.role === 'assistant'
          ? { ...message, content: message.content + content, phase: undefined }
          : message
      );
      return { messages };
    }),

  setMessageMetadata: (id, metadata) =>
    set((s) => {
      const messages = s.messages.map((message) =>
        message.id === id && message.role === 'assistant'
          ? { ...message, metadata, isStreaming: false, phase: undefined }
          : message
      );
      return { messages };
    }),

  setMessageStreaming: (id, streaming) =>
    set((s) => {
      const messages = s.messages.map((message) =>
        message.id === id && message.role === 'assistant'
          ? { ...message, isStreaming: streaming, phase: streaming ? message.phase : undefined }
          : message
      );
      return { messages };
    }),

  setMessagePhase: (id, phase) =>
    set((s) => {
      const messages = s.messages.map((message) =>
        message.id === id && message.role === 'assistant'
          ? { ...message, phase }
          : message
      );
      return { messages };
    }),

  setStreaming: (v) => set({ isStreaming: v }),

  setSessionId: (id) => set({ currentSessionId: id }),

  setGatewayParams: (params) =>
    set((s) => ({ gatewayParams: { ...s.gatewayParams, ...params } })),

  setAbortController: (ctrl) => set({ abortController: ctrl }),

  cancelStreaming: () => {
    get().abortController?.abort();
    set((s) => ({
      abortController: null,
      isStreaming: false,
      messages: s.messages.map((message) =>
        message.role === 'assistant' && message.isStreaming
          ? { ...message, isStreaming: false, phase: undefined }
          : message
      ),
    }));
  },

  clearMessages: () => set({ messages: [] }),

  buildRequest: (question) => {
    const s = get();
    return {
      ...s.gatewayParams,
      question,
      session_id: s.currentSessionId,
    };
  },
}));
