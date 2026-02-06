// API 客户端

import type { ApiResponse } from "@/types";

const API_BASE = "/api/v1";

const normalizeCodesParam = (codes: string[]) => {
  const uniq = Array.from(
    new Set((codes || []).map((c) => String(c || "").trim()).filter(Boolean))
  );
  uniq.sort();
  return uniq.join(",");
};

export const endpoints = {
  group: {
    list: () => `/group`,
  },
  stock: {
    list: (keyword: string) => `/stock/list?keyword=${encodeURIComponent(keyword)}`,
    followed: () => `/stock/follow`,
    followedItem: (stockCode: string) => `/stock/follow/${encodeURIComponent(stockCode)}`,
    realtime: (codes: string[]) => `/stock/realtime?codes=${normalizeCodesParam(codes)}`,
    rank: (
      sortBy: string = "change_percent",
      order: string = "desc",
      limit: number = 50,
      market: string = "all"
    ) =>
      `/stock/rank?sort_by=${encodeURIComponent(sortBy)}&order=${encodeURIComponent(order)}&limit=${limit}&market=${encodeURIComponent(market)}`,
    portfolioAnalysis: () => `/stock/portfolio/analysis`,
  },
  market: {
    overview: () => `/market/overview`,
    industryRank: (
      sortBy: string = "change_percent",
      order: string = "desc",
      limit: number = 20
    ) =>
      `/market/industry-rank?sort_by=${encodeURIComponent(sortBy)}&order=${encodeURIComponent(order)}&limit=${limit}`,
    conceptRank: (
      sortBy: string = "change_percent",
      order: string = "desc",
      limit: number = 20
    ) =>
      `/market/concept-rank?sort_by=${encodeURIComponent(sortBy)}&order=${encodeURIComponent(order)}&limit=${limit}`,
    industryMoneyFlow: (category: string = "hangye", sortBy: string = "main_inflow") =>
      `/market/industry-money-flow?category=${encodeURIComponent(category)}&sort_by=${encodeURIComponent(sortBy)}`,
    stockMoneyRank: (sortBy: string = "zjlr", limit: number = 50) =>
      `/market/stock-money-rank?sort_by=${encodeURIComponent(sortBy)}&limit=${limit}`,
    longTiger: (tradeDate?: string) =>
      tradeDate ? `/market/long-tiger?trade_date=${encodeURIComponent(tradeDate)}` : `/market/long-tiger`,
    limitStats: () => `/market/limit-stats`,
    northFlow: (days: number = 30) => `/market/north-flow?days=${days}`,
    moneyFlow: (
      sortBy: string = "main_net_inflow",
      order: string = "desc",
      limit: number = 20
    ) =>
      `/market/money-flow?sort_by=${encodeURIComponent(sortBy)}&order=${encodeURIComponent(order)}&limit=${limit}`,
  },
  ai: {
    chat: () => `/ai/chat`,
    chatStream: () => `/ai/chat/stream`,
    simpleStream: () => `/ai/simple/stream`,
    agentStream: () => `/ai/agent/stream`,
  },
};

type CachePolicy = {
  /** 内存缓存 TTL（毫秒）：用于页面切换/回退再进入的秒级加速 */
  ttlMs: number;
  /** localStorage 持久化 TTL（毫秒）：用于短时间反复进入的体验加速 */
  persistMs?: number;
  /** 网络失败时允许回退到（可能已过期的）缓存，避免页面全空 */
  allowStaleOnError?: boolean;
  /** 强制绕过缓存（用于用户主动“刷新/重试”） */
  force?: boolean;
};

type ChatMessage = { role: string; content: string };

type PersistedCacheEntry<T> = {
  v: 1;
  expireAt: number;
  savedAt: number;
  data: T;
};

const CACHE_VERSION: PersistedCacheEntry<unknown>["v"] = 1;
const STORAGE_PREFIX = "recon:api-cache:";

const memoryCache = new Map<string, { expireAt: number; data: unknown }>();
const inFlight = new Map<string, Promise<unknown>>();

const now = () => Date.now();
const canUseStorage = () => typeof window !== "undefined" && typeof window.localStorage !== "undefined";
const storageKey = (key: string) => `${STORAGE_PREFIX}${key}`;

const readStorageEntry = <T,>(key: string): PersistedCacheEntry<T> | null => {
  if (!canUseStorage()) return null;
  try {
    const raw = window.localStorage.getItem(storageKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedCacheEntry<T>;
    if (!parsed || parsed.v !== CACHE_VERSION || typeof parsed.expireAt !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
};

const writeStorageEntry = <T,>(key: string, entry: PersistedCacheEntry<T>) => {
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(storageKey(key), JSON.stringify(entry));
  } catch {
    // localStorage quota/禁用等场景：忽略持久化即可
  }
};

const removeStorageEntry = (key: string) => {
  if (!canUseStorage()) return;
  try {
    window.localStorage.removeItem(storageKey(key));
  } catch {
    // ignore
  }
};

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private cacheKey(endpoint: string) {
    return `${this.baseUrl}${endpoint}`;
  }

  /** 同步读取“未过期”的缓存（用于组件初始化快速回填）。 */
  peekCache<T>(endpoint: string): T | null {
    const key = this.cacheKey(endpoint);
    const mem = memoryCache.get(key);
    if (mem && mem.expireAt > now()) return mem.data as T;
    const persisted = readStorageEntry<T>(key);
    if (persisted && persisted.expireAt > now()) {
      memoryCache.set(key, { expireAt: persisted.expireAt, data: persisted.data as unknown });
      return persisted.data;
    }
    return null;
  }

  /** 失效单个 endpoint 的缓存（内存 + localStorage）。 */
  invalidate(endpoint: string) {
    const key = this.cacheKey(endpoint);
    memoryCache.delete(key);
    inFlight.delete(key);
    removeStorageEntry(key);
  }

  /** 按前缀失效缓存（用于批量清理某类请求）。 */
  invalidatePrefix(endpointPrefix: string) {
    const prefix = this.cacheKey(endpointPrefix);
    for (const k of Array.from(memoryCache.keys())) {
      if (k.startsWith(prefix)) memoryCache.delete(k);
    }
    for (const k of Array.from(inFlight.keys())) {
      if (k.startsWith(prefix)) inFlight.delete(k);
    }
    if (!canUseStorage()) return;
    try {
      const keys: string[] = [];
      for (let i = 0; i < window.localStorage.length; i += 1) {
        const k = window.localStorage.key(i);
        if (!k || !k.startsWith(STORAGE_PREFIX)) continue;
        const rawKey = k.slice(STORAGE_PREFIX.length);
        if (rawKey.startsWith(prefix)) keys.push(k);
      }
      for (const k of keys) window.localStorage.removeItem(k);
    } catch {
      // ignore
    }
  }

  private async parseErrorMessage(response: Response): Promise<string> {
    // 尝试解析后端错误信息（兼容 FastAPI HTTPException 的 {"detail": "..."} 与统一响应 {"message": "..."}）
    let message = `API Error: ${response.status} ${response.statusText}`;
    try {
      const errData: any = await response.json();
      if (errData && typeof errData.message === "string" && errData.message) message = errData.message;
      else if (errData && typeof errData.detail === "string" && errData.detail) message = errData.detail;
    } catch {
      // ignore
    }
    return message;
  }

  private async postStream(endpoint: string, body: unknown): Promise<Response> {
    const url = `${this.baseUrl}${endpoint}`;

    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      throw new Error("Network Error: Unable to connect to backend");
    }

    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response));
    }
    return response;
  }

  private async readSseDataLines(response: Response, onData: (data: string) => void): Promise<void> {
    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6);
        if (!data || data === "[DONE]") continue;
        onData(data);
      }
    }

    const tail = buffer.trim();
    if (tail.startsWith("data: ")) {
      const data = tail.slice(6);
      if (data && data !== "[DONE]") onData(data);
    }
  }

  private async streamContentFromSse(endpoint: string, body: unknown, onMessage?: (content: string) => void): Promise<string> {
    const response = await this.postStream(endpoint, body);
    let fullContent = "";

    await this.readSseDataLines(response, (data) => {
      try {
        const parsed = JSON.parse(data);
        if (parsed && typeof parsed.content === "string") {
          fullContent += parsed.content;
          onMessage?.(fullContent);
        }
      } catch (e) {
        console.warn("SSE JSON parse error:", e, "data:", data);
      }
    });

    return fullContent;
  }

  private async requestCached<T>(endpoint: string, policy: CachePolicy, options: RequestInit = {}): Promise<T> {
    const method = String(options.method || "GET").toUpperCase();
    if (method !== "GET") return this.request<T>(endpoint, options);

    const key = this.cacheKey(endpoint);

    if (!policy.force) {
      const mem = memoryCache.get(key);
      if (mem && mem.expireAt > now()) return mem.data as T;

      const persisted = readStorageEntry<T>(key);
      if (persisted && persisted.expireAt > now()) {
        memoryCache.set(key, { expireAt: persisted.expireAt, data: persisted.data as unknown });
        return persisted.data;
      }

      const inflight = inFlight.get(key);
      if (inflight) return inflight as Promise<T>;
    }

    let stale: T | null = null;
    if (policy.allowStaleOnError) {
      const mem = memoryCache.get(key);
      if (mem) stale = mem.data as T;
      if (stale == null) {
        const persisted = readStorageEntry<T>(key);
        if (persisted) stale = persisted.data;
      }
    }

    const p = this.request<T>(endpoint, options)
      .then((data) => {
        memoryCache.set(key, { expireAt: now() + Math.max(0, policy.ttlMs), data: data as unknown });
        if (policy.persistMs && policy.persistMs > 0) {
          writeStorageEntry<T>(key, { v: CACHE_VERSION, savedAt: now(), expireAt: now() + Math.max(0, policy.persistMs), data });
        }
        return data;
      })
      .catch((err) => {
        if (policy.allowStaleOnError && stale != null) return stale;
        throw err;
      })
      .finally(() => {
        inFlight.delete(key);
      });

    inFlight.set(key, p as Promise<unknown>);
    return p;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    let response: Response;
    try {
      response = await fetch(url, {
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
        ...options,
      });
    } catch (e) {
      throw new Error("Network Error: Unable to connect to backend");
    }

    if (!response.ok) {
      throw new Error(await this.parseErrorMessage(response));
    }

    let data: ApiResponse<T>;
    try {
      data = await response.json();
    } catch (e) {
      throw new Error("Invalid response: Server did not return valid JSON");
    }

    if (data.code !== 200 && data.code !== 0) {
      throw new Error(data.message || "API Error");
    }

    return data.data;
  }

  // ============ 股票 API ============

  async searchStock(keyword: string) {
    // 使用 /stock/list 接口，返回 {results: [...], total: number}
    const data = await this.request<{ results: any[]; total: number }>(endpoints.stock.list(keyword));
    return data.results || [];
  }

  async getFollowedStocks() {
    // 自选股列表变更频率低，但页面切换/返回频繁：启用缓存 + localStorage 持久化提升体验
    return this.requestCached<any>(
      endpoints.stock.followed(),
      { ttlMs: 30_000, persistMs: 24 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async addFollowStock(stockCode: string, stockName: string) {
    const resp = await this.request<any>(endpoints.stock.followed(), {
      method: "POST",
      body: JSON.stringify({ stock_code: stockCode, stock_name: stockName }),
    });
    this.invalidate(endpoints.stock.followed());
    return resp;
  }

  async removeFollowStock(stockCode: string) {
    const resp = await this.request<any>(endpoints.stock.followedItem(stockCode), {
      method: "DELETE",
    });
    this.invalidate(endpoints.stock.followed());
    // 列表/详情可能依赖该股票，清理相关缓存避免“已删除仍显示”
    this.invalidatePrefix(`/stock/detail/`);
    return resp;
  }

  async getRealtimeQuotes(codes: string[]) {
    return this.requestCached<any>(
      endpoints.stock.realtime(codes),
      { ttlMs: 10_000, persistMs: 30_000, allowStaleOnError: true }
    );
  }

  async getKlineData(code: string, period: string = "day", count: number = 100, adjust: string = "qfq") {
    return this.requestCached<any>(
      `/stock/${code}/kline?period=${period}&count=${count}&adjust=${adjust}`,
      { ttlMs: 5 * 60_000, persistMs: 30 * 60_000, allowStaleOnError: true }
    );
  }

  async getMinuteData(code: string) {
    return this.requestCached<any>(`/stock/${code}/minute`, { ttlMs: 20_000, persistMs: 2 * 60_000, allowStaleOnError: true });
  }

  async getChipDistribution(code: string) {
    return this.requestCached<any>(
      `/stock/${code}/chip-distribution`,
      { ttlMs: 5 * 60_000, persistMs: 60 * 60_000, allowStaleOnError: true }
    );
  }

  // ============ 股票详情 API (新增) ============

  async getStockDetail(code: string) {
    return this.requestCached<any>(
      `/stock/detail/${code}`,
      { ttlMs: 60_000, persistMs: 10 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockFundamental(code: string) {
    return this.requestCached<any>(
      `/stock/${code}/fundamental`,
      { ttlMs: 30_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockFinancial(code: string) {
    return this.requestCached<any>(
      `/stock/${code}/financial`,
      { ttlMs: 6 * 60 * 60_000, persistMs: 24 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockRating(code: string) {
    return this.requestCached<any>(
      `/stock/${code}/rating`,
      { ttlMs: 2 * 60 * 60_000, persistMs: 12 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockShareholders(code: string) {
    return this.requestCached<any>(
      `/stock/${code}/shareholders`,
      { ttlMs: 6 * 60 * 60_000, persistMs: 24 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockTopHolders(code: string, holderType: string = "float") {
    return this.requestCached<any>(
      `/stock/${code}/top-holders?holder_type=${holderType}`,
      { ttlMs: 6 * 60 * 60_000, persistMs: 24 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockDividend(code: string) {
    return this.requestCached<any>(
      `/stock/${code}/dividend`,
      { ttlMs: 12 * 60 * 60_000, persistMs: 48 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockMoneyFlowHistory(code: string, days: number = 30) {
    return this.requestCached<any>(
      `/stock/${code}/money-flow-history?days=${days}`,
      { ttlMs: 60_000, persistMs: 10 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockRank(sortBy: string = "change_percent", order: string = "desc", limit: number = 50, market: string = "all") {
    return this.requestCached<any>(
      endpoints.stock.rank(sortBy, order, limit, market),
      { ttlMs: 20_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getPortfolioAnalysis() {
    return this.requestCached<any>(
      endpoints.stock.portfolioAnalysis(),
      { ttlMs: 30_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  // ============ 市场 API ============

  async getIndustryRank(sortBy: string = "change_percent", order: string = "desc", limit: number = 20) {
    return this.requestCached<any>(
      endpoints.market.industryRank(sortBy, order, limit),
      { ttlMs: 30_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getMoneyFlow(sortBy: string = "main_net_inflow", order: string = "desc", limit: number = 20) {
    return this.requestCached<any>(
      endpoints.market.moneyFlow(sortBy, order, limit),
      { ttlMs: 20_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getConceptRank(sortBy: string = "change_percent", order: string = "desc", limit: number = 20) {
    return this.requestCached<any>(
      endpoints.market.conceptRank(sortBy, order, limit),
      { ttlMs: 30_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getLimitStats() {
    return this.requestCached<any>(endpoints.market.limitStats(), { ttlMs: 20_000, persistMs: 2 * 60_000, allowStaleOnError: true });
  }

  async getNorthFlow(days: number = 30) {
    return this.requestCached<any>(endpoints.market.northFlow(days), { ttlMs: 60_000, persistMs: 5 * 60_000, allowStaleOnError: true });
  }

  async getMarketOverview() {
    return this.requestCached<any>(endpoints.market.overview(), { ttlMs: 30_000, persistMs: 2 * 60_000, allowStaleOnError: true });
  }

  async getLongTiger(tradeDate?: string) {
    return this.requestCached<any>(
      endpoints.market.longTiger(tradeDate),
      { ttlMs: 60_000, persistMs: 10 * 60_000, allowStaleOnError: true }
    );
  }

  async getStockMoneyRank(sortBy: string = "zjlr", limit: number = 50) {
    return this.requestCached<any>(
      endpoints.market.stockMoneyRank(sortBy, limit),
      { ttlMs: 20_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getIndustryMoneyFlow(category: string = "hangye", sortBy: string = "main_inflow") {
    return this.requestCached<any>(
      endpoints.market.industryMoneyFlow(category, sortBy),
      { ttlMs: 20_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  // ============ 技术分析 API ============

  async getTechnicalAnalysis(code: string) {
    return this.requestCached<any>(
      `/technical/${code}`,
      { ttlMs: 30_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  async getBatchTechnicalAnalysis(codes: string[]) {
    return this.request<any>(`/technical/batch`, {
      method: "POST",
      body: JSON.stringify({ codes }),
    });
  }

  async getMACD(code: string) {
    return this.requestCached<any>(
      `/technical/${code}/macd`,
      { ttlMs: 30_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  async getRSI(code: string) {
    return this.requestCached<any>(
      `/technical/${code}/rsi`,
      { ttlMs: 30_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  async getTrend(code: string) {
    return this.requestCached<any>(
      `/technical/${code}/trend`,
      { ttlMs: 30_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  // ============ 数据源管理 API ============

  async getDataSources() {
    return this.request<any[]>(`/datasources`);
  }

  async getDataSourceConfigs() {
    return this.requestCached<any[]>(
      `/datasources/configs`,
      { ttlMs: 5 * 60_000, persistMs: 60 * 60_000, allowStaleOnError: true }
    );
  }

  async updateDataSource(name: string, config: any) {
    const resp = await this.request<any>(`/datasources/${name}`, {
      method: "PUT",
      body: JSON.stringify(config),
    });
    this.invalidate(`/datasources/configs`);
    return resp;
  }

  async resetDataSource(name: string) {
    const resp = await this.request<any>(`/datasources/${name}/reset`, {
      method: "POST",
    });
    this.invalidate(`/datasources/configs`);
    return resp;
  }

  async setDataSourcePriority(priority: string[]) {
    const resp = await this.request<any>(`/datasources/priority`, {
      method: "POST",
      body: JSON.stringify(priority),
    });
    this.invalidate(`/datasources/configs`);
    return resp;
  }

  // ============ 资讯 API ============

  async getLatestNews(source?: string, limit: number = 20) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (source) params.append("source", source);
    return this.requestCached<any>(
      `/news/latest?${params}`,
      { ttlMs: 30_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getTelegraph(page: number = 1, pageSize: number = 20) {
    return this.requestCached<any>(
      `/news/telegraph?page=${page}&page_size=${pageSize}`,
      { ttlMs: 30_000, persistMs: 2 * 60_000, allowStaleOnError: true }
    );
  }

  async getGlobalIndexes() {
    return this.requestCached<any>(
      `/news/global-indexes`,
      { ttlMs: 60_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  async getTradingViewNews(limit: number = 20) {
    return this.requestCached<any>(
      `/news/tradingview?limit=${limit}`,
      { ttlMs: 60_000, persistMs: 5 * 60_000, allowStaleOnError: true }
    );
  }

  async getTradingViewNewsDetail(newsId: string) {
    return this.requestCached<any>(
      `/news/tradingview/${encodeURIComponent(newsId)}`,
      { ttlMs: 6 * 60 * 60_000, persistMs: 24 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async searchNews(keyword: string, engine?: string, limit: number = 10) {
    const params = new URLSearchParams({ keyword, limit: String(limit) });
    if (engine) params.append("engine", engine);
    return this.request<any>(`/news/search?${params}`);
  }

  async getSearchEngines() {
    return this.requestCached<any>(
      `/news/search/engines`,
      { ttlMs: 5 * 60_000, persistMs: 60 * 60_000, allowStaleOnError: true }
    );
  }

  async addSearchEngine(config: { engine: string; api_key: string; enabled?: boolean; weight?: number; daily_limit?: number }) {
    const resp = await this.request<any>(`/news/search/engines`, {
      method: "POST",
      body: JSON.stringify(config),
    });
    this.invalidate(`/news/search/engines`);
    return resp;
  }

  async removeSearchEngine(configId: number) {
    const resp = await this.request<any>(`/news/search/engines/${configId}`, {
      method: "DELETE",
    });
    this.invalidate(`/news/search/engines`);
    return resp;
  }

  // ============ AI API ============

  async chat(question: string, stockCode?: string, modelId?: number, enableRetrieval: boolean = true) {
    return this.chatWithMessages([{ role: "user", content: question }], stockCode, modelId, enableRetrieval);
  }

  async chatWithMessages(messages: ChatMessage[], stockCode?: string, modelId?: number, enableRetrieval: boolean = true) {
    return this.request<any>(endpoints.ai.chat(), {
      method: "POST",
      body: JSON.stringify({
        messages,
        stock_code: stockCode,
        model_id: modelId,
        enable_retrieval: enableRetrieval,
      }),
    });
  }

  async chatStream(
    question: string,
    stockCode?: string,
    modelId?: number,
    enableRetrieval: boolean = true,
    onMessage?: (content: string) => void
  ): Promise<string> {
    return this.chatStreamWithMessages(
      [{ role: "user", content: question }],
      stockCode,
      modelId,
      enableRetrieval,
      onMessage
    );
  }

  async chatStreamWithMessages(
    messages: ChatMessage[],
    stockCode?: string,
    modelId?: number,
    enableRetrieval: boolean = true,
    onMessage?: (content: string) => void
  ): Promise<string> {
    return this.streamContentFromSse(
      endpoints.ai.chatStream(),
      {
        messages,
        stock_code: stockCode,
        model_id: modelId,
        stream: true,
        enable_retrieval: enableRetrieval,
      },
      onMessage
    );
  }

  async simpleAgentStreamWithMessages(
    messages: ChatMessage[],
    stockCode?: string,
    modelId?: number,
    enableRetrieval: boolean = true,
    onMessage?: (content: string) => void
  ): Promise<string> {
    return this.streamContentFromSse(
      endpoints.ai.simpleStream(),
      {
        messages,
        stock_code: stockCode,
        model_id: modelId,
        stream: true,
        enable_retrieval: enableRetrieval,
      },
      onMessage
    );
  }

  async agentWithMessages(
    messages: ChatMessage[],
    stockCode?: string,
    modelId?: number,
    enableRetrieval: boolean = true,
    mode: string = "agent",
    sessionId?: string
  ) {
    return this.request<any>(`/ai/agent`, {
      method: "POST",
      body: JSON.stringify({
        messages,
        stock_code: stockCode,
        model_id: modelId,
        enable_retrieval: enableRetrieval,
        mode,
        session_id: sessionId,
      }),
    });
  }

  async agentStreamWithMessages(
    messages: ChatMessage[],
    stockCode?: string,
    modelId?: number,
    enableRetrieval: boolean = true,
    sessionId?: string,
    mode: string = "agent",
    onEvent?: (event: any) => void
  ): Promise<string> {
    let finalAnswer = "";
    const response = await this.postStream(endpoints.ai.agentStream(), {
      messages,
      stock_code: stockCode,
      model_id: modelId,
      stream: true,
      enable_retrieval: enableRetrieval,
      session_id: sessionId,
      mode,
    });

    await this.readSseDataLines(response, (data) => {
      try {
        const evt = JSON.parse(data);
        onEvent?.(evt);
        if (evt && typeof evt === "object" && evt.type === "final_answer") {
          finalAnswer = String(evt.content || "");
        }
      } catch (e) {
        console.warn("Agent SSE JSON parse error:", e, "data:", data);
      }
    });

    return finalAnswer;
  }

  async getAIHistory(limit: number = 20) {
    return this.request<any>(`/ai/history?limit=${limit}`);
  }

  // ============ AI Session API ============

  async getAISession(sessionId: string, limit: number = 500) {
    return this.request<any>(`/ai/sessions/${encodeURIComponent(sessionId)}?limit=${limit}`);
  }

  async listAISessions(mode?: string, page: number = 1, pageSize: number = 20) {
    const params = new URLSearchParams();
    if (mode) params.set("mode", mode);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return this.request<any>(`/ai/sessions?${params.toString()}`);
  }

  async deleteAISession(sessionId: string) {
    return this.request<any>(`/ai/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  }

  async getAIConfigs() {
    return this.request<any>(`/settings/ai-configs`);
  }

  async createAIConfig(config: any) {
    return this.request<any>(`/settings/ai-configs`, {
      method: "POST",
      body: JSON.stringify(config),
    });
  }

  async updateAIConfig(id: number, config: any) {
    return this.request<any>(`/settings/ai-configs/${id}`, {
      method: "PUT",
      body: JSON.stringify(config),
    });
  }

  async deleteAIConfig(id: number) {
    return this.request<any>(`/settings/ai-configs/${id}`, {
      method: "DELETE",
    });
  }

  // ============ 设置 API ============

  async getSettings() {
    return this.requestCached<any>(
      `/settings`,
      { ttlMs: 5 * 60_000, persistMs: 60 * 60_000, allowStaleOnError: true }
    );
  }

  async updateSettings(settings: any) {
    const resp = await this.request<any>(`/settings`, {
      method: "PUT",
      body: JSON.stringify(settings),
    });
    this.invalidate(`/settings`);
    return resp;
  }

  async getVersion() {
    return this.request<any>(`/settings/version`);
  }

  async getSystemConfig() {
    return this.request<any>(`/settings/system`);
  }

  // ============ 分组 API ============

  async getGroups() {
    return this.requestCached<any>(
      `/group`,
      { ttlMs: 30_000, persistMs: 24 * 60 * 60_000, allowStaleOnError: true }
    );
  }

  async createGroup(name: string, description?: string) {
    const resp = await this.request<any>(`/group`, {
      method: "POST",
      body: JSON.stringify({ name, description }),
    });
    this.invalidate(`/group`);
    return resp;
  }

  async deleteGroup(id: number) {
    const resp = await this.request<any>(`/group/${id}`, {
      method: "DELETE",
    });
    this.invalidate(`/group`);
    return resp;
  }

  async addStockToGroup(groupId: number, stockCode: string) {
    const resp = await this.request<any>(`/group/${groupId}/stock?stock_code=${encodeURIComponent(stockCode)}`, {
      method: "POST",
    });
    this.invalidate(`/group`);
    return resp;
  }

  async removeStockFromGroup(groupId: number, stockCode: string) {
    const resp = await this.request<any>(`/group/${groupId}/stock/${stockCode}`, {
      method: "DELETE",
    });
    this.invalidate(`/group`);
    return resp;
  }

  // ============ 基金 API ============

  async getFollowedFunds() {
    return this.request<any>(`/fund/follow`);
  }

  async addFollowedFund(fundCode: string, fundName: string, fundType?: string) {
    return this.request<any>(`/fund/follow`, {
      method: "POST",
      body: JSON.stringify({ fund_code: fundCode, fund_name: fundName, fund_type: fundType }),
    });
  }

  async updateFollowedFund(fundCode: string, data: { fund_name?: string; cost_price?: number; hold_shares?: number; sort_order?: number }) {
    return this.request<any>(`/fund/follow/${fundCode}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async removeFollowedFund(fundCode: string) {
    return this.request<any>(`/fund/follow/${fundCode}`, {
      method: "DELETE",
    });
  }

  async searchFunds(keyword: string, fundType?: string, limit: number = 20) {
    const params = new URLSearchParams({ keyword, limit: String(limit) });
    if (fundType) params.append("fund_type", fundType);
    return this.request<any>(`/fund/list?${params}`);
  }

  async getFundDetail(fundCode: string) {
    return this.request<any>(`/fund/${fundCode}`);
  }

  async getFundNetValue(fundCode: string, days: number = 30) {
    return this.request<any>(`/fund/${fundCode}/net-value?days=${days}`);
  }
}

// 导出单例
export const api = new ApiClient();
export default api;
