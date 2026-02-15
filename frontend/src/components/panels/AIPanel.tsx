"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import ReactMarkdown from "react-markdown";
import api from "@/lib/api";

type PanelMode = "chat" | "analysis";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface HistoryItem {
  id: number;
  question: string;
  response: string;
  model_name: string;
  created_at: string;
}

interface AIConfig {
  id: number;
  name: string;
  enabled: boolean;
}

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}

function normalizeAIConfig(raw: unknown): AIConfig | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const id = Number(obj.id);
  if (!Number.isFinite(id) || id <= 0) return null;

  const nameRaw = obj.name;
  const enabledRaw = obj.enabled;
  return {
    id,
    name: typeof nameRaw === "string" && nameRaw.trim() ? nameRaw : `模型#${id}`,
    enabled: enabledRaw === undefined ? true : Boolean(enabledRaw),
  };
}

function normalizeHistoryItem(raw: unknown): HistoryItem | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const id = Number(obj.id);
  const question = typeof obj.question === "string" ? obj.question : "";
  const response = typeof obj.response === "string" ? obj.response : "";
  const modelName = typeof obj.model_name === "string" ? obj.model_name : "AI";
  const createdAt = typeof obj.created_at === "string" ? obj.created_at : "";
  if (!Number.isFinite(id) || !question || !response) return null;

  return {
    id,
    question,
    response,
    model_name: modelName,
    created_at: createdAt,
  };
}

export default function AIPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState("");
  const [mode, setMode] = useState<PanelMode>("chat");
  const [selectedModel, setSelectedModel] = useState<number | undefined>(undefined);
  const [aiConfigs, setAIConfigs] = useState<AIConfig[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [enableRetrieval, setEnableRetrieval] = useState(true);

  // 使用ref追踪是否已初始化，避免无限循环
  const initializedRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // 获取AI配置和历史 - 移除selectedModel依赖避免无限循环
  const fetchData = useCallback(async () => {
    try {
      const [rawConfigs, historyData] = await Promise.all([
        api.getAIConfigs().catch(() => []),
        api.getAIHistory(20).catch(() => ({ items: [] })),
      ]);

      const normalizedConfigs = (Array.isArray(rawConfigs) ? rawConfigs : [])
        .map(normalizeAIConfig)
        .filter((item): item is AIConfig => item !== null);

      const historyRaw =
        historyData &&
        typeof historyData === "object" &&
        Array.isArray((historyData as { items?: unknown[] }).items)
          ? (historyData as { items: unknown[] }).items
          : [];

      const normalizedHistory = historyRaw
        .map(normalizeHistoryItem)
        .filter((item): item is HistoryItem => item !== null);

      setAIConfigs(normalizedConfigs);
      setHistory(normalizedHistory);

      // 仅在首次加载时设置默认模型
      if (!initializedRef.current) {
        const enabledConfig = normalizedConfigs.find((config) => config.enabled);
        if (enabledConfig) {
          setSelectedModel(enabledConfig.id);
        }
        initializedRef.current = true;
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 新消息/流式内容变化时自动滚动到底部（避免用户手动拖动）
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" });
  }, [messages, streaming]);

  const refreshHistory = async () => {
    try {
      const historyData = await api.getAIHistory(20);
      const historyRaw =
        historyData &&
        typeof historyData === "object" &&
        Array.isArray((historyData as { items?: unknown[] }).items)
          ? (historyData as { items: unknown[] }).items
          : [];

      setHistory(
        historyRaw
          .map(normalizeHistoryItem)
          .filter((item): item is HistoryItem => item !== null)
      );
    } catch {
      // ignore
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);
    setStreaming("");

    const outgoingMessages = [...messages, { role: "user" as const, content: userMessage }];

    try {
      if (mode === "analysis") {
        setStreaming("正在分析中…");
        const response = await api.simpleAgentStreamWithMessages(
          [{ role: "user" as const, content: userMessage }],
          undefined,
          selectedModel,
          enableRetrieval,
          (content) => setStreaming(content)
        );
        setMessages((prev) => [...prev, { role: "assistant", content: response || "（无可用回答）" }]);
        setStreaming("");
      } else {
        const response = await api.chatStreamWithMessages(
          outgoingMessages,
          undefined,
          selectedModel,
          enableRetrieval,
          (content) => setStreaming(content)
        );
        setMessages((prev) => [...prev, { role: "assistant", content: response }]);
        setStreaming("");
      }
      refreshHistory();
    } catch (error: unknown) {
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${toErrorMessage(error, "请求失败")}` }]);
    } finally {
      setLoading(false);
    }
  };

  const loadHistoryItem = (item: HistoryItem) => {
    setMessages([
      { role: "user", content: item.question },
      { role: "assistant", content: item.response },
    ]);
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return "刚刚";
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    if (days < 7) return `${days}天前`;
    return date.toLocaleDateString();
  };

  const enabledConfigs = aiConfigs.filter((config) => config.enabled);

  return (
    <div className="h-full flex">
      {/* 历史记录侧栏 */}
      <div className="w-64 border-r bg-gray-50 flex flex-col">
        <div className="p-4 border-b bg-white">
          <h3 className="font-medium text-sm text-gray-700">对话历史</h3>
        </div>
        <div className="flex-1 overflow-y-auto">
          {history.length === 0 ? (
            <div className="p-4 text-center text-gray-400 text-sm">暂无历史记录</div>
          ) : (
            history.map((item) => (
              <div
                key={item.id}
                onClick={() => loadHistoryItem(item)}
                className="px-4 py-3 border-b hover:bg-white cursor-pointer transition-colors"
              >
                <div className="text-sm font-medium truncate">{item.question}</div>
                <div className="text-xs text-gray-400 mt-1 flex justify-between">
                  <span>{item.model_name || "AI"}</span>
                  <span>{formatTime(item.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* 主聊天区域 */}
      <div className="flex-1 flex flex-col">
        {/* 顶部: 模型选择 */}
        <div className="p-4 border-b bg-white flex items-center justify-between">
          <h1 className="text-lg font-bold">AI 助手</h1>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">模式:</span>
              <select
                value={mode}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === "chat" || value === "analysis") setMode(value);
                }}
                className="px-3 py-1.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="chat">对话</option>
                <option value="analysis">分析</option>
              </select>
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={enableRetrieval}
                onChange={(e) => setEnableRetrieval(e.target.checked)}
              />
              <span>联网检索</span>
            </label>

            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">模型:</span>
              <select
                value={selectedModel !== undefined ? String(selectedModel) : ""}
                onChange={(e) => {
                  const value = e.target.value;
                  if (!value) {
                    setSelectedModel(undefined);
                    return;
                  }
                  const nextValue = Number(value);
                  setSelectedModel(Number.isFinite(nextValue) ? nextValue : undefined);
                }}
                className="px-3 py-1.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {enabledConfigs.map((config) => (
                  <option key={config.id} value={config.id}>{config.name}</option>
                ))}
                {enabledConfigs.length === 0 && (
                  <option value="">请先配置AI模型</option>
                )}
              </select>
            </div>
          </div>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
          {messages.length === 0 && !streaming && (
            <div className="h-full flex flex-col items-center justify-center text-gray-400">
              <svg className="w-16 h-16 mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
              <p>开始和AI助手对话吧</p>
              <p className="text-sm mt-2">可以询问股票分析、市场行情等问题</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] px-4 py-3 rounded-xl ${msg.role === "user" ? "bg-blue-600 text-white" : "bg-white shadow-sm"}`}>
                {msg.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-a:text-blue-600 prose-code:text-pink-600 prose-code:bg-pink-50 prose-code:px-1 prose-code:rounded prose-pre:bg-gray-800 prose-pre:text-gray-100">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}
              </div>
            </div>
          ))}

          {streaming && (
            <div className="flex justify-start">
              <div className="max-w-[80%] px-4 py-3 rounded-xl bg-white shadow-sm">
                <div className="prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-a:text-blue-600 prose-code:text-pink-600 prose-code:bg-pink-50 prose-code:px-1 prose-code:rounded prose-pre:bg-gray-800 prose-pre:text-gray-100">
                  <ReactMarkdown>{streaming}</ReactMarkdown>
                </div>
                <div className="text-xs text-gray-400 mt-1">正在输入...</div>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* 输入框 */}
        <div className="p-4 border-t bg-white">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="输入问题..."
              disabled={loading}
              className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "发送中..." : "发送"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
