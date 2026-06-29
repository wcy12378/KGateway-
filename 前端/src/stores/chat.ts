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
  updateLastAssistant: (content: string) => void;
  setLastMessageMetadata: (metadata: ChatMessage['metadata']) => void;
  setLastMessageStreaming: (streaming: boolean) => void;
  setStreaming: (v: boolean) => void;
  setSessionId: (id: string) => void;
  setGatewayParams: (params: Partial<ChatState['gatewayParams']>) => void;
  setAbortController: (ctrl: AbortController | null) => void;
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

  updateLastAssistant: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + content };
      }
      return { messages: msgs };
    }),

  setLastMessageMetadata: (metadata) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, metadata, isStreaming: false };
      }
      return { messages: msgs };
    }),

  setLastMessageStreaming: (streaming) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, isStreaming: streaming };
      }
      return { messages: msgs };
    }),

  setStreaming: (v) => set({ isStreaming: v }),

  setSessionId: (id) => set({ currentSessionId: id }),

  setGatewayParams: (params) =>
    set((s) => ({ gatewayParams: { ...s.gatewayParams, ...params } })),

  setAbortController: (ctrl) => set({ abortController: ctrl }),

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
