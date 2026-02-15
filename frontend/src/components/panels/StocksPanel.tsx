"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import api, { endpoints } from "@/lib/api";
import StockDetailPanel from "@/components/StockDetail";
import KLineChart from "@/components/KLineChart";
import StockMinuteChart from "@/components/charts/StockMinuteChart";
import StockMoneyFlowChart from "@/components/charts/StockMoneyFlowChart";
import ChipDistributionChart from "@/components/charts/ChipDistributionChart";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/ToastProvider";

interface StockQuote {
  stock_code: string;
  stock_name: string;
  current_price: number;
  change_percent: number;
  volume: number;
  amount: number;
}

interface FollowedStock {
  stock_code: string;
  stock_name: string;
  cost_price: number;
  volume: number;
  alert_price_min: number;
  alert_price_max: number;
}

interface StockSearchResult {
  stock_code: string;
  stock_name: string;
  exchange?: string;
  industry?: string;
}

interface GroupStockRef {
  stock_code: string;
  sort_order: number;
}

interface StockGroup {
  id: number;
  name: string;
  description?: string;
  sort_order: number;
  stocks: GroupStockRef[];
}

interface RealtimeQuotesPayload {
  quotes?: StockQuote[];
}

type AlertFrequency = "always" | "once" | "never";

type AlertRuntimeSettings = {
  enabled: boolean;
  frequency: AlertFrequency;
  windowMinutes: number;
};

type AlertEditorState = {
  code: string;
  name?: string;
  min: string;
  max: string;
};

type AlertPersistedState = {
  v: 1;
  keys: Record<string, number>;
};

type PortfolioPosition = {
  stock_code: string;
  stock_name: string;
  cost_price: number;
  current_price: number | null;
  volume: number;
  cost: number;
  market_value: number | null;
  profit: number | null;
  profit_percent: number | null;
  change_percent: number | null;
};

type PortfolioAnalysis = {
  total_cost: number;
  total_market_value: number | null;
  total_profit: number | null;
  total_profit_percent: number | null;
  position_count: number;
  missing_quote_count: number;
  positions: PortfolioPosition[];
};

type PositionEditorState = {
  code: string;
  costPrice: string;
  volume: string;
};

type TechSignal =
  | "strong_buy"
  | "buy"
  | "weak_buy"
  | "hold"
  | "weak_sell"
  | "sell"
  | "strong_sell";

type TechSnapshot = {
  stock_code: string;
  buy_signal: TechSignal;
  score: number | null;
  summary?: string;
  updated_at: number; // ms timestamp
};

type TechFilter = "all" | "buy" | "hold" | "sell" | "unscanned";

const ALERT_STATE_STORAGE_KEY = "stock_recon_alert_state_v1";

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (error && typeof error === "object" && "message" in error) {
    const msg = (error as { message?: unknown }).message;
    if (typeof msg === "string" && msg) return msg;
  }
  return fallback;
}

function getLocalDayKey(date: Date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function loadAlertStateKeys(): Record<string, number> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(ALERT_STATE_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const v = (parsed as { v?: unknown }).v;
    const keys = (parsed as { keys?: unknown }).keys;
    if (v !== 1 || !keys || typeof keys !== "object") return {};

    const out: Record<string, number> = {};
    for (const [k, value] of Object.entries(keys as Record<string, unknown>)) {
      const n = typeof value === "number" ? value : Number(value);
      if (Number.isFinite(n) && n > 0) out[k] = n;
    }
    return out;
  } catch {
    return {};
  }
}

function saveAlertStateKeys(keys: Record<string, number>) {
  if (typeof window === "undefined") return;
  try {
    const payload: AlertPersistedState = { v: 1, keys };
    localStorage.setItem(ALERT_STATE_STORAGE_KEY, JSON.stringify(payload));
  } catch { /* ignore */ }
}

function formatAlertSummary(stock: FollowedStock): string {
  const min = stock.alert_price_min > 0 ? `≤${stock.alert_price_min.toFixed(2)}` : "";
  const max = stock.alert_price_max > 0 ? `≥${stock.alert_price_max.toFixed(2)}` : "";
  return [min, max].filter(Boolean).join(" ") || "未设置";
}

function formatPrice(v: number | null | undefined, digits: number = 2): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "-";
  return v.toFixed(digits);
}

function formatMoneyYuan(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "-";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return v.toFixed(2);
}

function formatPct(v: number | null | undefined, digits: number = 2): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function formatTimeHHMM(ts: number | null | undefined): string {
  if (typeof ts !== "number" || !Number.isFinite(ts) || ts <= 0) return "-";
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

const TECH_SIGNAL_META: Record<TechSignal, { label: string; cls: string }> = {
  strong_buy: { label: "强买", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" },
  buy: { label: "买入", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" },
  weak_buy: { label: "关注", cls: "bg-blue-50 text-blue-700 border-blue-100" },
  hold: { label: "观望", cls: "bg-gray-50 text-gray-700 border-gray-200" },
  weak_sell: { label: "减仓", cls: "bg-amber-50 text-amber-800 border-amber-100" },
  sell: { label: "卖出", cls: "bg-red-50 text-red-700 border-red-100" },
  strong_sell: { label: "强卖", cls: "bg-red-50 text-red-700 border-red-100" },
};

const normalizeTechSignal = (value: unknown): TechSignal | null => {
  if (typeof value !== "string") return null;
  const v = value.trim().toLowerCase();
  if (v === "strong_buy" || v === "buy" || v === "weak_buy" || v === "hold" || v === "weak_sell" || v === "sell" || v === "strong_sell") {
    return v as TechSignal;
  }
  return null;
};

const isTechBuy = (s: TechSignal) => s === "strong_buy" || s === "buy" || s === "weak_buy";
const isTechSell = (s: TechSignal) => s === "weak_sell" || s === "sell" || s === "strong_sell";

const toStringOrUndefined = (value: unknown): string | undefined => {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

const toNumberOr = (value: unknown, fallback: number): number => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
};

const toNumberOrNull = (value: unknown): number | null => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
};

const normalizePortfolioPosition = (raw: unknown): PortfolioPosition | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const stockCode = toStringOrUndefined(obj.stock_code);
  if (!stockCode) return null;
  return {
    stock_code: stockCode,
    stock_name: toStringOrUndefined(obj.stock_name) || stockCode,
    cost_price: Math.max(0, toNumberOr(obj.cost_price, 0)),
    current_price: toNumberOrNull(obj.current_price),
    volume: Math.max(0, Math.floor(toNumberOr(obj.volume, 0))),
    cost: Math.max(0, toNumberOr(obj.cost, 0)),
    market_value: toNumberOrNull(obj.market_value),
    profit: toNumberOrNull(obj.profit),
    profit_percent: toNumberOrNull(obj.profit_percent),
    change_percent: toNumberOrNull(obj.change_percent),
  };
};

const normalizePortfolioAnalysis = (raw: unknown): PortfolioAnalysis | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const positions = (Array.isArray(obj.positions) ? obj.positions : [])
    .map(normalizePortfolioPosition)
    .filter((item): item is PortfolioPosition => item !== null);

  return {
    total_cost: Math.max(0, toNumberOr(obj.total_cost, 0)),
    total_market_value: toNumberOrNull(obj.total_market_value),
    total_profit: toNumberOrNull(obj.total_profit),
    total_profit_percent: toNumberOrNull(obj.total_profit_percent),
    position_count: Math.max(0, Math.floor(toNumberOr(obj.position_count, positions.length))),
    missing_quote_count: Math.max(0, Math.floor(toNumberOr(obj.missing_quote_count, 0))),
    positions,
  };
};

const normalizeFollowedStock = (raw: unknown): FollowedStock | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const stockCode = toStringOrUndefined(obj.stock_code);
  if (!stockCode) return null;
  return {
    stock_code: stockCode,
    stock_name: toStringOrUndefined(obj.stock_name) || stockCode,
    cost_price: Math.max(0, toNumberOr(obj.cost_price, 0)),
    volume: Math.max(0, Math.floor(toNumberOr(obj.volume, 0))),
    alert_price_min: Math.max(0, toNumberOr(obj.alert_price_min, 0)),
    alert_price_max: Math.max(0, toNumberOr(obj.alert_price_max, 0)),
  };
};

const normalizeStockSearchResult = (raw: unknown): StockSearchResult | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const stockCode = toStringOrUndefined(obj.stock_code);
  const stockName = toStringOrUndefined(obj.stock_name);
  if (!stockCode || !stockName) return null;
  return {
    stock_code: stockCode,
    stock_name: stockName,
    exchange: toStringOrUndefined(obj.exchange),
    industry: toStringOrUndefined(obj.industry),
  };
};

const normalizeGroupStock = (raw: unknown): GroupStockRef | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const stockCode = toStringOrUndefined(obj.stock_code);
  if (!stockCode) return null;
  return {
    stock_code: stockCode,
    sort_order: toNumberOr(obj.sort_order, 0),
  };
};

const normalizeGroup = (raw: unknown): StockGroup | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const id = toNumberOr(obj.id, NaN);
  const name = toStringOrUndefined(obj.name);
  if (!Number.isFinite(id) || !name) return null;
  const stocks = (Array.isArray(obj.stocks) ? obj.stocks : [])
    .map(normalizeGroupStock)
    .filter((item): item is GroupStockRef => item !== null);

  return {
    id,
    name,
    description: toStringOrUndefined(obj.description),
    sort_order: toNumberOr(obj.sort_order, 0),
    stocks,
  };
};

const normalizeQuote = (raw: unknown): StockQuote | null => {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const stockCode = toStringOrUndefined(obj.stock_code);
  if (!stockCode) return null;
  return {
    stock_code: stockCode,
    stock_name: toStringOrUndefined(obj.stock_name) || stockCode,
    current_price: toNumberOr(obj.current_price, 0),
    change_percent: toNumberOr(obj.change_percent, 0),
    volume: toNumberOr(obj.volume, 0),
    amount: toNumberOr(obj.amount, 0),
  };
};

const dedupeStocks = (rawList: unknown[]): FollowedStock[] => {
  const uniq = new Map<string, FollowedStock>();
  for (const item of rawList) {
    const stock = normalizeFollowedStock(item);
    if (!stock) continue;
    if (!uniq.has(stock.stock_code)) uniq.set(stock.stock_code, stock);
  }
  return Array.from(uniq.values());
};

const buildQuotesMap = (payload: unknown): Record<string, StockQuote> => {
  const obj = payload && typeof payload === "object" ? (payload as RealtimeQuotesPayload) : null;
  const rows = Array.isArray(obj?.quotes) ? obj.quotes : [];
  const quotesMap: Record<string, StockQuote> = {};
  for (const row of rows) {
    const quote = normalizeQuote(row);
    if (!quote) continue;
    quotesMap[quote.stock_code] = quote;
  }
  return quotesMap;
};

const isOverseaStockCode = (code: string): boolean => {
  const v = (code || "").trim().toLowerCase();
  return v.startsWith("hk") || v.startsWith("us");
};

const normalizeClientStockCode = (code: string): string => {
  const raw = (code || "").trim();
  if (!raw) return "";

  const lower = raw.toLowerCase();
  if (lower.startsWith("sh")) return `sh${raw.slice(2).trim()}`;
  if (lower.startsWith("sz")) return `sz${raw.slice(2).trim()}`;
  if (lower.startsWith("hk")) return `hk${raw.slice(2).trim()}`;
  if (lower.startsWith("us")) return `us${raw.slice(2).trim().toUpperCase()}`;

  if (/^\d+$/.test(raw)) {
    if (raw.startsWith("6")) return `sh${raw}`;
    if (raw.startsWith("0") || raw.startsWith("3")) return `sz${raw}`;
  }

  return raw;
};

export default function StocksPanel({ active = true, initialCode }: { active?: boolean; initialCode?: string }) {
  const toast = useToast();
  const [stocks, setStocks] = useState<FollowedStock[]>([]);
  const [quotes, setQuotes] = useState<Record<string, StockQuote>>({});
  const [loading, setLoading] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchActiveIndex, setSearchActiveIndex] = useState(0);
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const dedupeWarnedRef = useRef(false);
  const alertSettingsRef = useRef<AlertRuntimeSettings>({
    enabled: true,
    frequency: "always",
    windowMinutes: 10,
  });
  const alertStateRef = useRef<Record<string, number> | null>(null);

  // 分组相关状态
  const [groups, setGroups] = useState<StockGroup[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<number | null>(null);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");

  const [removeStockConfirm, setRemoveStockConfirm] = useState<{ code: string; name?: string } | null>(null);
  const [deleteGroupConfirm, setDeleteGroupConfirm] = useState<{ id: number; name: string } | null>(null);
  const [alertEditor, setAlertEditor] = useState<AlertEditorState | null>(null);
  const [alertSaving, setAlertSaving] = useState(false);
  const [portfolioOpen, setPortfolioOpen] = useState(false);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [portfolioError, setPortfolioError] = useState("");
  const [portfolio, setPortfolio] = useState<PortfolioAnalysis | null>(null);
  const [positionEditor, setPositionEditor] = useState<PositionEditorState>({ code: "", costPrice: "", volume: "" });
  const [positionSaving, setPositionSaving] = useState(false);

  const [manualAddOpen, setManualAddOpen] = useState(false);
  const [manualAddCode, setManualAddCode] = useState("");
  const [manualAddName, setManualAddName] = useState("");
  const [manualAddSaving, setManualAddSaving] = useState(false);

  // 技术扫描：批量技术分析（用于自选股快速过一遍信号/分数）
  const [techMap, setTechMap] = useState<Record<string, TechSnapshot>>({});
  const [techScanning, setTechScanning] = useState(false);
  const [techProgress, setTechProgress] = useState<{ done: number; total: number; failed: number }>({ done: 0, total: 0, failed: 0 });
  const [techFailedCodes, setTechFailedCodes] = useState<string[]>([]);
  const [techScanError, setTechScanError] = useState("");
  const [techFilter, setTechFilter] = useState<TechFilter>("all");
  const [listSort, setListSort] = useState<"default" | "change" | "pnl" | "tech">("default");
  const [techUpdatedAt, setTechUpdatedAt] = useState<number | null>(null);
  const techScanIdRef = useRef(0);

  // 允许通过 /stocks?code=xxx 直接打开个股详情（便于从榜单/Scanner 跳转）
  useEffect(() => {
    const v = (initialCode || "").trim();
    if (!v) return;
    const normalized = normalizeClientStockCode(v);
    if (!normalized) return;
    setSelectedStock(normalized);
  }, [initialCode]);

  // 获取分组
  const fetchGroups = useCallback(async () => {
    try {
      const data = await api.getGroups();
      const normalizedGroups = (Array.isArray(data) ? data : [])
        .map(normalizeGroup)
        .filter((item): item is StockGroup => item !== null);
      setGroups(normalizedGroups);
    } catch { /* ignore */ }
  }, []);

  const getAlertState = () => {
    if (alertStateRef.current) return alertStateRef.current;
    const loaded = loadAlertStateKeys();
    alertStateRef.current = loaded;
    return loaded;
  };

  // 价格提醒：基于“自选股提醒价 + 实时行情”在前端做最小提示（toast），不依赖后端推送通道
  const checkPriceAlerts = useCallback((stockList: FollowedStock[], quotesMap: Record<string, StockQuote>) => {
    const settings = alertSettingsRef.current;
    if (!settings.enabled || settings.frequency === "never") return;

    const now = Date.now();
    const windowMs = Math.max(0, settings.windowMinutes) * 60_000;
    const dayKey = getLocalDayKey();
    const state = getAlertState();

    const events: { key: string; message: string }[] = [];

    const maybeAdd = (stock: FollowedStock, type: "price_low" | "price_high", threshold: number, message: string) => {
      const baseKey = `${stock.stock_code}:${type}:${threshold}`;
      const key = settings.frequency === "once" ? `${dayKey}:${baseKey}` : baseKey;
      const lastAt = state[key];
      if (settings.frequency === "once") {
        if (lastAt) return;
      } else if (lastAt && windowMs > 0 && now - lastAt < windowMs) {
        return;
      }
      state[key] = now;
      events.push({ key, message });
    };

    for (const stock of stockList) {
      const quote = quotesMap[stock.stock_code];
      const price = quote?.current_price;
      if (typeof price !== "number" || !Number.isFinite(price) || price <= 0) continue;

      if (stock.alert_price_min > 0 && price <= stock.alert_price_min) {
        maybeAdd(
          stock,
          "price_low",
          stock.alert_price_min,
          `${stock.stock_name}（${stock.stock_code}）现价 ${price.toFixed(2)} 跌破提醒价 ${stock.alert_price_min.toFixed(2)}`
        );
      }

      if (stock.alert_price_max > 0 && price >= stock.alert_price_max) {
        maybeAdd(
          stock,
          "price_high",
          stock.alert_price_max,
          `${stock.stock_name}（${stock.stock_code}）现价 ${price.toFixed(2)} 突破提醒价 ${stock.alert_price_max.toFixed(2)}`
        );
      }
    }

    if (events.length === 0) return;
    saveAlertStateKeys(state);

    const maxToasts = 3;
    for (const ev of events.slice(0, maxToasts)) {
      toast.push({ variant: "warning", title: "价格提醒", message: ev.message });
    }
    if (events.length > maxToasts) {
      toast.push({ variant: "info", title: "价格提醒", message: `还有 ${events.length - maxToasts} 条提醒触发（已折叠）` });
    }
  }, [toast]);

  const fetchStocks = useCallback(async () => {
    try {
      // 后端 /stock/follow 返回数组 (Response[List[FollowedStockResponse]])
      const data = await api.getFollowedStocks();
      const rawList = Array.isArray(data) ? data : [];

      const stockList = dedupeStocks(rawList);
      if (rawList.length !== stockList.length) {
        if (!dedupeWarnedRef.current) {
          dedupeWarnedRef.current = true;
          toast.push({ variant: "warning", title: "数据异常", message: "自选股列表存在重复代码，已在前端自动去重显示。" });
        }
      }

      setStocks(stockList);
      if (stockList.length > 0) {
        const codes = stockList.map((s) => s.stock_code);
        // 后端返回 {quotes: [...]}，字段为 stock_code/current_price/...
        const quotesData = await api.getRealtimeQuotes(codes);
        const quotesMap = buildQuotesMap(quotesData);
        setQuotes(quotesMap);
        checkPriceAlerts(stockList, quotesMap);
      }
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [toast, checkPriceAlerts]);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | undefined;

    const start = async () => {
      try {
        const cachedGroups = api.peekCache<StockGroup[]>(endpoints.group.list());
        if (Array.isArray(cachedGroups) && cachedGroups.length > 0) {
          const normalizedCachedGroups = cachedGroups
            .map(normalizeGroup)
            .filter((item): item is StockGroup => item !== null);
          if (normalizedCachedGroups.length > 0) setGroups(normalizedCachedGroups);
        }
      } catch { /* ignore */ }

      try {
        const cachedFollow = api.peekCache<FollowedStock[]>(endpoints.stock.followed());
        const rawList = Array.isArray(cachedFollow) ? cachedFollow : [];
        if (rawList.length > 0) {
          const stockList = dedupeStocks(rawList);
          setStocks(stockList);
          setLoading(false);

          const codes = stockList.map((s) => s.stock_code);
          const cachedQuotes = api.peekCache<RealtimeQuotesPayload>(endpoints.stock.realtime(codes));
          if (cachedQuotes) {
            setQuotes(buildQuotesMap(cachedQuotes));
          }
        }
      } catch { /* ignore */ }

      try { await fetchGroups(); } catch { /* ignore */ }
      try { await fetchStocks(); } catch { /* ignore */ }

      let refreshSeconds = 30;
      try {
        const settings = await api.getSettings();
        const v = Number(settings?.refresh_interval);
        if (Number.isFinite(v) && v > 0) refreshSeconds = v;

        // 同步提醒策略：开启/频率/窗口（窗口用于 always 模式下避免 toast 刷屏）
        const enabled = Boolean(settings?.open_alert ?? true);
        const rawFreq = String(settings?.alert_frequency || "always").trim().toLowerCase();
        const frequency: AlertFrequency = rawFreq === "once" || rawFreq === "never" ? rawFreq : "always";
        const win = toNumberOr(settings?.alert_window_duration, 10);
        alertSettingsRef.current = {
          enabled,
          frequency,
          windowMinutes: Number.isFinite(win) && win > 0 ? win : 10,
        };
      } catch { /* ignore */ }

      if (cancelled) return;
      interval = setInterval(fetchStocks, Math.max(1, refreshSeconds) * 1000);
    };

    start();
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [active, fetchGroups, fetchStocks]);

  useEffect(() => {
    if (!searchOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      const el = searchRef.current;
      if (!el) return;
      if (!el.contains(e.target as Node)) setSearchOpen(false);
    };
    window.addEventListener("mousedown", onMouseDown);
    return () => window.removeEventListener("mousedown", onMouseDown);
  }, [searchOpen]);

  useEffect(() => {
    if (!showGroupModal) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setShowGroupModal(false);
      setNewGroupName("");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showGroupModal]);

  useEffect(() => {
    if (!manualAddOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      if (manualAddSaving) return;
      setManualAddOpen(false);
      setManualAddCode("");
      setManualAddName("");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [manualAddOpen, manualAddSaving]);

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    try {
      const results = await api.searchStock(searchKeyword);
      const list = (Array.isArray(results) ? results : [])
        .map(normalizeStockSearchResult)
        .filter((item): item is StockSearchResult => item !== null);
      setSearchResults(list);
      setSearchOpen(list.length > 0);
      setSearchActiveIndex(0);
    } catch { /* ignore */ }
  };

  const handleAdd = async (code: string, name: string) => {
    try {
      await api.addFollowStock(code, name);
      setSearchResults([]);
      setSearchOpen(false);
      setSearchKeyword("");
      fetchStocks();
      toast.push({ variant: "success", title: "已添加", message: `${name}（${code}）已加入自选股` });
    } catch { /* ignore */ }
  };

  const openManualAdd = () => {
    setManualAddCode(searchKeyword.trim());
    setManualAddName("");
    setManualAddOpen(true);
  };

  const saveManualAdd = async () => {
    const code = manualAddCode.trim();
    const name = manualAddName.trim();
    if (!code) {
      toast.push({ variant: "warning", title: "请输入代码", message: "示例：sh600519 / hk00700 / usAAPL" });
      return;
    }

    setManualAddSaving(true);
    try {
      await api.addFollowStock(code, name);
      setManualAddOpen(false);
      setManualAddCode("");
      setManualAddName("");
      setSearchResults([]);
      setSearchOpen(false);
      setSearchKeyword("");
      fetchStocks();
      toast.push({ variant: "success", title: "已添加", message: name ? `${name}（${code}）已加入自选股` : `${code} 已加入自选股` });
    } catch (errorObject: unknown) {
      toast.push({ variant: "error", title: "添加失败", message: toErrorMessage(errorObject, "请稍后重试") });
    } finally {
      setManualAddSaving(false);
    }
  };

  const handleRemove = async (code: string, name?: string) => {
    try {
      await api.removeFollowStock(code);
      fetchStocks();
      toast.push({ variant: "success", title: "已移除", message: name ? `${name}（${code}）已移除` : `${code} 已移除` });
    } catch { /* ignore */ }
  };

  const openAlertEditorFor = (stock: FollowedStock) => {
    setAlertEditor({
      code: stock.stock_code,
      name: stock.stock_name,
      min: stock.alert_price_min > 0 ? String(stock.alert_price_min) : "",
      max: stock.alert_price_max > 0 ? String(stock.alert_price_max) : "",
    });
  };

  const parseAlertInput = (value: string): number => {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return n;
  };

  const saveAlertEditor = async () => {
    if (!alertEditor) return;
    const min = parseAlertInput(alertEditor.min);
    const max = parseAlertInput(alertEditor.max);
    if (min > 0 && max > 0 && min >= max) {
      toast.push({ variant: "warning", title: "参数不合理", message: "提醒下限应小于上限" });
      return;
    }

    setAlertSaving(true);
    try {
      await api.setStockAlert(alertEditor.code, min, max);
      setStocks((prev) =>
        prev.map((s) =>
          s.stock_code === alertEditor.code
            ? { ...s, alert_price_min: min, alert_price_max: max }
            : s
        )
      );
      toast.push({
        variant: "success",
        title: "已保存",
        message: `${alertEditor.name ? `${alertEditor.name}（${alertEditor.code}）` : alertEditor.code} 提醒已更新`,
      });
      setAlertEditor(null);
    } catch (errorObject: unknown) {
      toast.push({ variant: "error", title: "保存失败", message: toErrorMessage(errorObject, "请稍后重试") });
    } finally {
      setAlertSaving(false);
    }
  };

  const refreshPortfolio = useCallback(async (force: boolean = false) => {
    setPortfolioLoading(true);
    setPortfolioError("");
    try {
      if (force) api.invalidate(endpoints.stock.portfolioAnalysis());
      const data = await api.getPortfolioAnalysis();
      const normalized = normalizePortfolioAnalysis(data);
      if (!normalized) throw new Error("组合分析返回数据格式异常");
      setPortfolio(normalized);
    } catch (errorObject: unknown) {
      const msg = toErrorMessage(errorObject, "获取组合分析失败");
      setPortfolio(null);
      setPortfolioError(msg);
    } finally {
      setPortfolioLoading(false);
    }
  }, []);

  const setPositionEditorCode = (code: string) => {
    const stock = stocks.find((s) => s.stock_code === code);
    setPositionEditor({
      code,
      costPrice: stock && stock.cost_price > 0 ? String(stock.cost_price) : "",
      volume: stock && stock.volume > 0 ? String(stock.volume) : "",
    });
  };

  const openPortfolio = () => {
    const defaultCode = (selectedStock || positionEditor.code || stocks[0]?.stock_code || "").trim();
    if (defaultCode && defaultCode !== positionEditor.code) setPositionEditorCode(defaultCode);
    setPortfolioOpen(true);
    refreshPortfolio();
  };

  const parseCostPrice = (value: string): number => {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return n;
  };

  const parseVolume = (value: string): number => {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return Math.floor(n);
  };

  const savePosition = async () => {
    const code = positionEditor.code.trim();
    if (!code) {
      toast.push({ variant: "warning", title: "缺少股票", message: "请选择要设置持仓的股票" });
      return;
    }
    const price = parseCostPrice(positionEditor.costPrice);
    const vol = parseVolume(positionEditor.volume);

    const bothZero = price === 0 && vol === 0;
    const bothPositive = price > 0 && vol > 0;
    if (!bothZero && !bothPositive) {
      toast.push({ variant: "warning", title: "参数不完整", message: "成本价与持仓数量需要同时填写（或都填 0 清除持仓）" });
      return;
    }

    setPositionSaving(true);
    try {
      await api.setCostPriceAndVolume(code, price, vol);
      setStocks((prev) => prev.map((s) => (s.stock_code === code ? { ...s, cost_price: price, volume: vol } : s)));
      toast.push({
        variant: "success",
        title: bothZero ? "已清除" : "已保存",
        message: bothZero ? `${code} 持仓已清除` : `${code} 持仓已更新`,
      });
      await refreshPortfolio(true);
    } catch (errorObject: unknown) {
      toast.push({ variant: "error", title: "保存失败", message: toErrorMessage(errorObject, "请稍后重试") });
    } finally {
      setPositionSaving(false);
    }
  };

  // 创建分组
  const handleCreateGroup = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await api.createGroup(name);
      setNewGroupName("");
      setShowGroupModal(false);
      fetchGroups();
      toast.push({ variant: "success", title: "分组已创建", message: `已创建分组「${name}」` });
    } catch { /* ignore */ }
  };

  // 删除分组
  const handleDeleteGroup = async (id: number, name?: string) => {
    try {
      await api.deleteGroup(id);
      if (selectedGroup === id) setSelectedGroup(null);
      fetchGroups();
      toast.push({ variant: "success", title: "分组已删除", message: name ? `已删除分组「${name}」` : "已删除分组" });
    } catch { /* ignore */ }
  };

  // 添加股票到分组
  const handleAddToGroup = async (groupId: number, stockCode: string) => {
    try {
      await api.addStockToGroup(groupId, stockCode);
      fetchGroups();
    } catch { /* ignore */ }
  };

  // 从分组移除股票
  const handleRemoveFromGroup = async (groupId: number, stockCode: string) => {
    try {
      await api.removeStockFromGroup(groupId, stockCode);
      fetchGroups();
    } catch { /* ignore */ }
  };

  const formatChange = (v: number | null) => v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const changeColor = (v: number | null) => v == null ? "text-gray-500" : v > 0 ? "text-red-600" : v < 0 ? "text-green-600" : "text-gray-500";

  // 根据选中分组过滤股票
  const filteredStocks = selectedGroup
    ? stocks.filter((s) => {
        const group = groups.find((g) => g.id === selectedGroup);
        return group?.stocks.some((gs) => gs.stock_code === s.stock_code);
      })
    : stocks;

  const selectedStockInfo = selectedStock ? stocks.find((s) => s.stock_code === selectedStock) : null;
  const positionCount = stocks.filter((s) => s.cost_price > 0 && s.volume > 0).length;
  const selectedOversea = selectedStock ? isOverseaStockCode(selectedStock) : false;

  // 技术扫描统计与筛选（仅作用于当前列表/分组）
  const techStats = (() => {
    let buy = 0;
    let hold = 0;
    let sell = 0;
    let unscanned = 0;

    for (const s of filteredStocks) {
      const signal = techMap[s.stock_code]?.buy_signal;
      if (!signal) unscanned += 1;
      else if (isTechBuy(signal)) buy += 1;
      else if (signal === "hold") hold += 1;
      else if (isTechSell(signal)) sell += 1;
      else unscanned += 1;
    }

    return { total: filteredStocks.length, buy, hold, sell, unscanned };
  })();

  const matchTechFilter = (signal: TechSignal | null | undefined): boolean => {
    if (techFilter === "all") return true;
    if (techFilter === "unscanned") return !signal;
    if (!signal) return false;
    if (techFilter === "buy") return isTechBuy(signal);
    if (techFilter === "hold") return signal === "hold";
    return isTechSell(signal);
  };

  const displayedStocks = filteredStocks.filter((s) => matchTechFilter(techMap[s.stock_code]?.buy_signal));

  const sortedStocks = (() => {
    const arr = [...displayedStocks];
    if (listSort === "default") return arr;

    const baseIndex = new Map<string, number>();
    for (let i = 0; i < filteredStocks.length; i += 1) {
      baseIndex.set(filteredStocks[i].stock_code, i);
    }

    const asNumberOrNull = (v: unknown): number | null => {
      if (typeof v === "number" && Number.isFinite(v)) return v;
      if (typeof v === "string") {
        const s = v.trim();
        if (!s) return null;
        const n = Number(s);
        return Number.isFinite(n) ? n : null;
      }
      return null;
    };

    const getChange = (s: FollowedStock): number | null => asNumberOrNull(quotes[s.stock_code]?.change_percent);
    const getTechScore = (s: FollowedStock): number | null => asNumberOrNull(techMap[s.stock_code]?.score);
    const getPnlPct = (s: FollowedStock): number | null => {
      if (!(s.cost_price > 0 && s.volume > 0)) return null;
      const current = asNumberOrNull(quotes[s.stock_code]?.current_price);
      if (current == null) return null;
      return ((current / s.cost_price) - 1) * 100;
    };

    const getKey = (s: FollowedStock): number | null => {
      if (listSort === "change") return getChange(s);
      if (listSort === "pnl") return getPnlPct(s);
      return getTechScore(s);
    };

    arr.sort((a, b) => {
      const ka = getKey(a);
      const kb = getKey(b);
      if (ka == null && kb == null) return (baseIndex.get(a.stock_code) ?? 0) - (baseIndex.get(b.stock_code) ?? 0);
      if (ka == null) return 1;
      if (kb == null) return -1;
      if (kb !== ka) return kb - ka; // desc
      return (baseIndex.get(a.stock_code) ?? 0) - (baseIndex.get(b.stock_code) ?? 0);
    });

    return arr;
  })();

  const chipClass = (active: boolean) =>
    `px-3 py-1 text-xs rounded-full border whitespace-nowrap transition-colors ${
      active
        ? "bg-[var(--accent)] text-white border-transparent"
        : "bg-white text-gray-600 border-[color:var(--border-color)] hover:bg-[var(--bg-surface-muted)]"
    }`;

  const runTechScan = async () => {
    if (techScanning) return;

    const uniqCodes = Array.from(new Set(filteredStocks.map((s) => s.stock_code).filter(Boolean)));
    if (uniqCodes.length === 0) {
      toast.push({ variant: "warning", title: "暂无股票", message: "当前列表没有可扫描的股票" });
      return;
    }

    const MAX_SCAN = 100;
    const codes = uniqCodes.slice(0, MAX_SCAN);
    if (uniqCodes.length > MAX_SCAN) {
      toast.push({ variant: "info", title: "技术扫描", message: `当前列表较多，本次仅扫描前 ${MAX_SCAN} 只（共 ${uniqCodes.length}）` });
    }

    const scanId = techScanIdRef.current + 1;
    techScanIdRef.current = scanId;

    setTechScanning(true);
    setTechScanError("");
    setTechFailedCodes([]);
    setTechProgress({ done: 0, total: codes.length, failed: 0 });

    let done = 0;
    let ok = 0;
    const failedAll: string[] = [];
    let errorHit: string | null = null;

    for (let i = 0; i < codes.length; i += 20) {
      const chunk = codes.slice(i, i + 20);
      try {
        const resp = await api.getBatchTechnicalAnalysis(chunk);
        if (techScanIdRef.current !== scanId) return;

        const obj = resp && typeof resp === "object" ? (resp as Record<string, unknown>) : {};
        const rawResults = Array.isArray(obj.results) ? (obj.results as unknown[]) : [];
        const rawFailed = Array.isArray(obj.failed) ? (obj.failed as unknown[]) : [];

        const nowTs = Date.now();
        const chunkMap: Record<string, TechSnapshot> = {};

        for (const raw of rawResults) {
          if (!raw || typeof raw !== "object") continue;
          const it = raw as Record<string, unknown>;
          const code = typeof it.stock_code === "string" ? it.stock_code.trim() : "";
          const signal = normalizeTechSignal(it.buy_signal);
          if (!code || !signal) continue;

          const score = toNumberOrNull(it.score);
          const summary = typeof it.summary === "string" && it.summary.trim() ? it.summary : undefined;
          chunkMap[code] = { stock_code: code, buy_signal: signal, score, summary, updated_at: nowTs };
        }

        const failedChunk: string[] = [];
        for (const f of rawFailed) {
          if (typeof f === "string" && f.trim()) failedChunk.push(f.trim());
        }

        ok += Object.keys(chunkMap).length;
        if (Object.keys(chunkMap).length > 0 || failedChunk.length > 0) {
          setTechMap((prev) => {
            const next = { ...prev, ...chunkMap };
            for (const c of failedChunk) delete next[c];
            return next;
          });
        }

        if (failedChunk.length > 0) failedAll.push(...failedChunk);

        done += chunk.length;
        setTechFailedCodes([...failedAll]);
        setTechProgress({ done, total: codes.length, failed: failedAll.length });
      } catch (errorObject: unknown) {
        const msg = toErrorMessage(errorObject, "技术扫描失败");
        errorHit = msg;
        setTechScanError(msg);
        toast.push({ variant: "error", title: "技术扫描失败", message: msg });
        break;
      }
    }

    if (techScanIdRef.current !== scanId) return;
    setTechUpdatedAt(Date.now());
    setTechScanning(false);

    if (!errorHit) {
      toast.push({
        variant: failedAll.length > 0 ? "warning" : "success",
        title: "技术扫描完成",
        message: `成功 ${ok} / 失败 ${failedAll.length}（港/美股或数据源异常可能导致失败）`,
      });
    }
  };

  return (
    <div className="h-full flex flex-col lg:flex-row">
      {/* 股票列表 */}
      <div className={`w-full lg:w-80 border-r bg-white flex flex-col ${selectedStock ? "hidden lg:flex" : "flex"}`}>
        {/* 分组标签 */}
        <div className="p-2 border-b bg-[var(--bg-surface-muted)] flex items-center gap-2 overflow-x-auto">
          <button
            type="button"
            onClick={() => setSelectedGroup(null)}
            className={`px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
              selectedGroup === null ? "bg-[var(--accent)] text-white" : "bg-white text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white"
            }`}
          >
            全部 ({stocks.length})
          </button>
          {groups.map((group) => (
            <div key={group.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setSelectedGroup(group.id)}
                className={`px-3 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
                  selectedGroup === group.id ? "bg-[var(--accent)] text-white" : "bg-white text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-white"
                }`}
              >
                {group.name} ({group.stocks?.length || 0})
              </button>
              <button
                type="button"
                onClick={() => setDeleteGroupConfirm({ id: group.id, name: group.name })}
                className="icon-btn p-1 text-[var(--text-muted)] hover:text-red-600 hover:bg-white"
                aria-label={`删除分组 ${group.name}`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setShowGroupModal(true)}
            className="px-2 py-1 text-xs text-[var(--accent)] hover:bg-white rounded-full whitespace-nowrap transition-colors duration-200 cursor-pointer"
          >
            + 新建
          </button>
        </div>

        {/* 搜索框 */}
        <div className="p-4 border-b">
          <div className="relative" ref={searchRef}>
            <input
              type="text"
              value={searchKeyword}
              onChange={(e) => {
                const v = e.target.value;
                setSearchKeyword(v);
                setSearchResults([]);
                setSearchOpen(false);
                setSearchActiveIndex(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setSearchOpen(false);
                  return;
                }
                if (e.key === "ArrowDown") {
                  if (searchResults.length === 0) return;
                  e.preventDefault();
                  setSearchOpen(true);
                  setSearchActiveIndex((i) => Math.min(searchResults.length - 1, i + 1));
                  return;
                }
                if (e.key === "ArrowUp") {
                  if (searchResults.length === 0) return;
                  e.preventDefault();
                  setSearchOpen(true);
                  setSearchActiveIndex((i) => Math.max(0, i - 1));
                  return;
                }
                if (e.key === "Enter") {
                  if (searchOpen && searchResults.length > 0) {
                    const item = searchResults[searchActiveIndex];
                    if (item) handleAdd(item.stock_code, item.stock_name);
                    return;
                  }
                  handleSearch();
                }
              }}
              placeholder="搜索股票..."
              className="input pl-9"
              role="combobox"
              aria-autocomplete="list"
              aria-haspopup="listbox"
              aria-label="搜索股票"
              aria-expanded={searchOpen && searchResults.length > 0}
              aria-controls="stock-search-results"
              aria-activedescendant={searchOpen ? `stock-search-option-${searchActiveIndex}` : undefined}
            />
            <svg className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {/* 搜索下拉菜单 - 移到relative容器内部 */}
	            {searchOpen && searchResults.length > 0 && (
	              <div
	                id="stock-search-results"
	                role="listbox"
	                className="absolute z-10 left-0 right-0 mt-1 bg-white border border-[color:var(--border-color)] rounded-lg shadow-lg max-h-56 overflow-y-auto"
	              >
                {searchResults.map((item, idx) => {
                  const active = idx === searchActiveIndex;
                  return (
                    <div
                      key={`${item.stock_code}-${idx}`}
                      id={`stock-search-option-${idx}`}
                      role="option"
                      aria-selected={active}
                      onMouseEnter={() => setSearchActiveIndex(idx)}
                      onClick={() => handleAdd(item.stock_code, item.stock_name)}
                      className={`px-4 py-2 text-sm cursor-pointer transition-colors duration-200 ${
                        active ? "bg-[var(--bg-surface-muted)]" : "hover:bg-[var(--bg-surface-muted)]"
                      }`}
                    >
                      <span className="font-medium">{item.stock_name}</span>{" "}
                      <span className="text-[var(--text-muted)] font-mono">{item.stock_code}</span>
                    </div>
                  );
                })}
	              </div>
	            )}
	          </div>

            <div className="mt-2 flex items-center justify-end">
              <button
                type="button"
                onClick={openManualAdd}
                className="text-xs text-[var(--accent)] hover:opacity-90"
                title="示例：sh600519 / hk00700 / usAAPL（名称可留空自动补全）"
              >
                手动添加（港/美股）
              </button>
            </div>

            <div className="mt-3 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <button type="button" onClick={openPortfolio} className="btn btn-secondary">
                    组合分析
                  </button>
                  <button type="button" onClick={runTechScan} disabled={techScanning} className="btn btn-secondary" title="对当前列表做批量技术分析（最多100只）">
                    {techScanning ? `技术扫描 ${techProgress.done}/${techProgress.total}` : "技术扫描"}
                  </button>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-xs text-gray-500">
                    持仓 {positionCount}/{stocks.length}
                  </div>
                  <select
                    value={listSort}
                    onChange={(e) => setListSort(e.target.value as "default" | "change" | "pnl" | "tech")}
                    className="px-2 py-1 text-xs border border-[color:var(--border-color)] rounded-lg bg-white text-gray-600"
                    aria-label="列表排序"
                    title="列表排序"
                  >
                    <option value="default">默认排序</option>
                    <option value="change">按涨跌幅</option>
                    <option value="pnl">按盈亏%</option>
                    <option value="tech">按技术分</option>
                  </select>
                  <button type="button" onClick={fetchStocks} className="text-xs text-gray-500 hover:text-gray-800">
                    刷新
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <div className="text-xs text-gray-500">技术筛选</div>
                <button type="button" onClick={() => setTechFilter("all")} className={chipClass(techFilter === "all")}>
                  全部 {techStats.total}
                </button>
                <button type="button" onClick={() => setTechFilter("buy")} className={chipClass(techFilter === "buy")}>
                  买入 {techStats.buy}
                </button>
                <button type="button" onClick={() => setTechFilter("hold")} className={chipClass(techFilter === "hold")}>
                  观望 {techStats.hold}
                </button>
                <button type="button" onClick={() => setTechFilter("sell")} className={chipClass(techFilter === "sell")}>
                  卖出 {techStats.sell}
                </button>
                <button type="button" onClick={() => setTechFilter("unscanned")} className={chipClass(techFilter === "unscanned")}>
                  未扫描 {techStats.unscanned}
                </button>
                {techUpdatedAt ? (
                  <span className="text-xs text-gray-400">更新 {formatTimeHHMM(techUpdatedAt)}</span>
                ) : null}
                {techFailedCodes.length > 0 ? (
                  <span className="text-xs text-amber-700">失败 {techFailedCodes.length}</span>
                ) : null}
              </div>

              {techScanError ? (
                <div role="alert" className="p-3 rounded-lg bg-amber-50 text-amber-800 text-sm border border-amber-100">
                  {techScanError}
                </div>
              ) : null}
            </div>
	        </div>

        {/* 股票列表 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-center text-gray-400">加载中...</div>
          ) : filteredStocks.length === 0 ? (
            <div className="p-4 text-center text-gray-400">
              {selectedGroup ? "该分组暂无股票" : "暂无自选股"}
            </div>
          ) : sortedStocks.length === 0 ? (
            <div className="p-4 text-center text-gray-400">
              <div>当前筛选暂无股票</div>
              <button type="button" onClick={() => setTechFilter("all")} className="mt-2 text-xs text-[var(--accent)] hover:opacity-90">
                清除筛选
              </button>
            </div>
          ) : (
            sortedStocks.map((stock) => {
              const quote = quotes[stock.stock_code];
              const tech = techMap[stock.stock_code];
              const techMeta = tech ? TECH_SIGNAL_META[tech.buy_signal] : null;

              const hasPosition = stock.cost_price > 0 && stock.volume > 0;
              const current = quote?.current_price;
              const pnl =
                hasPosition && typeof current === "number" && Number.isFinite(current)
                  ? (current - stock.cost_price) * stock.volume
                  : null;
              const pnlPct =
                hasPosition && typeof current === "number" && Number.isFinite(current) && stock.cost_price > 0
                  ? ((current / stock.cost_price) - 1) * 100
                  : null;
              const pnlCls = pnl == null ? "text-gray-400" : pnl > 0 ? "text-red-600" : pnl < 0 ? "text-green-600" : "text-gray-500";

              return (
                <div
                  key={stock.stock_code}
                  onClick={() => setSelectedStock(stock.stock_code)}
                  className={`px-4 py-3 border-b cursor-pointer transition-colors duration-200 ${selectedStock === stock.stock_code ? "bg-[var(--bg-surface-muted)]" : "hover:bg-[var(--bg-surface-muted)]"}`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="font-medium text-sm">{stock.stock_name}</div>
                      <div className="text-xs text-gray-400">{stock.stock_code}</div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono text-sm ${changeColor(quote?.change_percent)}`}>{quote?.current_price?.toFixed(2) || "-"}</div>
                      <div className={`text-xs font-mono ${changeColor(quote?.change_percent)}`}>{formatChange(quote?.change_percent)}</div>
                      {techMeta ? (
                        <div className="mt-1 flex items-center justify-end gap-1">
                          <span className={`px-2 py-0.5 text-[11px] rounded-md border ${techMeta.cls}`}>{techMeta.label}</span>
                          {typeof tech?.score === "number" && Number.isFinite(tech.score) ? (
                            <span className="text-[11px] font-mono text-gray-400">{tech.score}</span>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  {/* 分组操作 */}
                  {groups.length > 0 && (
                    <div className="mt-2 flex gap-1 flex-wrap">
                      {groups.map((group) => {
                        const inGroup = group.stocks.some((gs) => gs.stock_code === stock.stock_code);
                        return (
                          <button
                            key={group.id}
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (inGroup) {
                                handleRemoveFromGroup(group.id, stock.stock_code);
                              } else {
                                handleAddToGroup(group.id, stock.stock_code);
                              }
                            }}
                            className={`px-2 py-0.5 text-xs rounded transition-colors ${
                              inGroup ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                            }`}
                          >
                            {inGroup ? group.name : `+ ${group.name}`}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* 价格提醒 */}
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        openAlertEditorFor(stock);
                      }}
                      className="px-2 py-0.5 text-xs rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
                      aria-label="设置价格提醒"
                    >
                      提醒
                    </button>
                    <div className="text-xs text-gray-400 font-mono">{formatAlertSummary(stock)}</div>
                  </div>

                  {stock.cost_price > 0 && stock.volume > 0 ? (
                    <div className="mt-1 text-xs text-gray-400 font-mono">
                      持仓：{stock.volume} @ {stock.cost_price.toFixed(2)}
                    </div>
                  ) : null}

                  {pnl != null ? (
                    <div className={`mt-1 text-xs font-mono ${pnlCls}`}>
                      盈亏：{formatMoneyYuan(pnl)}（{formatPct(pnlPct)}）
                    </div>
                  ) : null}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 详情区域 */}
      <div className={`flex-1 overflow-y-auto ${selectedStock ? "block" : "hidden lg:block"}`}>
        {selectedStock ? (
          <div>
            <div className="lg:hidden sticky top-0 z-10 bg-white border-b border-[color:var(--border-color)] px-4 py-3 flex items-center gap-2">
              <button type="button" onClick={() => setSelectedStock(null)} className="icon-btn -ml-2" aria-label="返回股票列表">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">{selectedStockInfo?.stock_name || selectedStock}</div>
                <div className="text-xs text-[var(--text-muted)] font-mono truncate">{selectedStock}</div>
              </div>
            </div>

            <div className="p-6 space-y-4">
            <StockDetailPanel
              code={selectedStock}
              onRemove={selectedStockInfo ? () => {
                setRemoveStockConfirm({ code: selectedStock, name: selectedStockInfo?.stock_name });
              } : undefined}
            />
            <KLineChart code={selectedStock} />
            {selectedOversea ? (
              <div className="bg-white rounded-xl shadow-sm p-4 text-sm text-gray-500">
                港/美股当前仅展示：行情、日周月K线、决策仪表盘；分时/资金/筹码等数据源暂未接入。
              </div>
            ) : (
              <>
                <StockMinuteChart code={selectedStock} />
                <StockMoneyFlowChart code={selectedStock} />
                <ChipDistributionChart code={selectedStock} />
              </>
            )}
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center text-gray-400">
            选择一只股票查看详情
          </div>
        )}
      </div>

      {/* 新建分组弹窗 */}
      {showGroupModal && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onMouseDown={() => {
            setShowGroupModal(false);
            setNewGroupName("");
          }}
        >
          <div className="card bg-white p-6 w-80 shadow-xl" onMouseDown={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-medium mb-4">新建分组</h3>
            <input
              type="text"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateGroup()}
              placeholder="输入分组名称..."
              className="input mb-4"
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setShowGroupModal(false); setNewGroupName(""); }}
                className="btn btn-secondary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleCreateGroup}
                disabled={!newGroupName.trim()}
                className="btn btn-primary"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 手动添加弹窗（支持港/美股） */}
      {manualAddOpen && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onMouseDown={() => {
            if (manualAddSaving) return;
            setManualAddOpen(false);
            setManualAddCode("");
            setManualAddName("");
          }}
        >
          <div className="card bg-white p-6 w-full max-w-[520px] shadow-xl" onMouseDown={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-lg font-medium">手动添加自选股</h3>
                <div className="mt-1 text-xs text-gray-500">示例：sh600519 / hk00700 / usAAPL（名称可留空自动补全）</div>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label="关闭"
                onClick={() => {
                  if (manualAddSaving) return;
                  setManualAddOpen(false);
                  setManualAddCode("");
                  setManualAddName("");
                }}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">股票代码</label>
                <input
                  value={manualAddCode}
                  onChange={(e) => setManualAddCode(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveManualAdd()}
                  placeholder="例如 usAAPL"
                  className="input"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">股票名称（可选）</label>
                <input
                  value={manualAddName}
                  onChange={(e) => setManualAddName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveManualAdd()}
                  placeholder="留空将尝试通过行情接口补全"
                  className="input"
                />
              </div>
            </div>

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  if (manualAddSaving) return;
                  setManualAddOpen(false);
                  setManualAddCode("");
                  setManualAddName("");
                }}
                className="btn btn-secondary"
                disabled={manualAddSaving}
              >
                取消
              </button>
              <button type="button" onClick={saveManualAdd} className="btn btn-primary" disabled={manualAddSaving}>
                {manualAddSaving ? "添加中..." : "添加"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 价格提醒弹窗 */}
      {alertEditor && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onMouseDown={() => {
            if (alertSaving) return;
            setAlertEditor(null);
          }}
        >
          <div
            className="card bg-white p-6 w-full max-w-[520px] shadow-xl"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-lg font-medium">价格提醒</h3>
                <div className="mt-1 text-xs text-gray-500 break-words">
                  {alertEditor.name ? `${alertEditor.name}（${alertEditor.code}）` : alertEditor.code}
                </div>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label="关闭"
                onClick={() => {
                  if (alertSaving) return;
                  setAlertEditor(null);
                }}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">下限（跌破提醒）</label>
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={alertEditor.min}
                  onChange={(e) => setAlertEditor((prev) => (prev ? { ...prev, min: e.target.value } : prev))}
                  placeholder="留空或 0 表示不提醒"
                  className="input"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">上限（突破提醒）</label>
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={alertEditor.max}
                  onChange={(e) => setAlertEditor((prev) => (prev ? { ...prev, max: e.target.value } : prev))}
                  placeholder="留空或 0 表示不提醒"
                  className="input"
                />
              </div>
            </div>

            <div className="mt-3 text-xs text-gray-500">
              说明：留空或 0 表示不提醒；提醒频率/窗口在「系统设置」中配置（{getLocalDayKey()}）。
            </div>

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setAlertEditor((prev) => (prev ? { ...prev, min: "", max: "" } : prev))}
                disabled={alertSaving}
                className="btn btn-secondary"
              >
                清空
              </button>
              <button
                type="button"
                onClick={() => setAlertEditor(null)}
                disabled={alertSaving}
                className="btn btn-secondary"
              >
                取消
              </button>
              <button
                type="button"
                onClick={saveAlertEditor}
                disabled={alertSaving}
                className="btn btn-primary"
              >
                {alertSaving ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 组合分析弹窗 */}
      {portfolioOpen && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onMouseDown={() => {
            if (portfolioLoading || positionSaving) return;
            setPortfolioOpen(false);
          }}
        >
          <div
            className="card bg-white p-6 w-full max-w-[920px] max-h-[90vh] overflow-y-auto shadow-xl"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-lg font-medium">组合分析</h3>
                <div className="mt-1 text-xs text-gray-500">
                  仅统计已录入成本价与持仓数量的自选股；行情缺失时，汇总值将显示为“—”避免误导。
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => refreshPortfolio(true)}
                  disabled={portfolioLoading}
                >
                  {portfolioLoading ? "刷新中..." : "刷新"}
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="关闭"
                  onClick={() => {
                    if (portfolioLoading || positionSaving) return;
                    setPortfolioOpen(false);
                  }}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {portfolioError && (
              <div role="alert" className="mt-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm border border-red-100">
                {portfolioError}
              </div>
            )}

            {!portfolioError && portfolioLoading && (
              <div className="mt-6 text-center text-gray-400">加载组合分析中...</div>
            )}

            {!portfolioError && !portfolioLoading && portfolio && (
              <div className="mt-4 space-y-4">
                {/* 汇总 */}
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <div className="bg-[var(--bg-surface-muted)] rounded-xl p-3">
                    <div className="text-xs text-gray-500">总成本</div>
                    <div className="mt-1 font-mono font-semibold">{formatMoneyYuan(portfolio.total_cost)}</div>
                  </div>
                  <div className="bg-[var(--bg-surface-muted)] rounded-xl p-3">
                    <div className="text-xs text-gray-500">总市值</div>
                    <div className="mt-1 font-mono font-semibold">{formatMoneyYuan(portfolio.total_market_value)}</div>
                  </div>
                  <div className="bg-[var(--bg-surface-muted)] rounded-xl p-3">
                    <div className="text-xs text-gray-500">总盈亏</div>
                    <div className={`mt-1 font-mono font-semibold ${changeColor(portfolio.total_profit)}`}>{formatMoneyYuan(portfolio.total_profit)}</div>
                  </div>
                  <div className="bg-[var(--bg-surface-muted)] rounded-xl p-3">
                    <div className="text-xs text-gray-500">总盈亏率</div>
                    <div className={`mt-1 font-mono font-semibold ${changeColor(portfolio.total_profit_percent)}`}>{formatPct(portfolio.total_profit_percent)}</div>
                  </div>
                  <div className="bg-[var(--bg-surface-muted)] rounded-xl p-3">
                    <div className="text-xs text-gray-500">持仓数 / 缺失</div>
                    <div className="mt-1 font-mono font-semibold">{portfolio.position_count} / {portfolio.missing_quote_count}</div>
                  </div>
                </div>

                {/* 明细 */}
                <div className="bg-white rounded-xl border border-[color:var(--border-color)] overflow-hidden">
                  <div className="px-4 py-3 bg-[var(--bg-surface-muted)] text-sm font-medium text-gray-900">
                    持仓明细
                  </div>
                  {portfolio.positions.length === 0 ? (
                    <div className="p-4 text-sm text-gray-500">
                      暂无持仓明细。请在下方录入成本价与持仓数量后再查看。
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="text-gray-500">
                          <tr className="border-b">
                            <th className="text-left px-4 py-2">股票</th>
                            <th className="text-right px-4 py-2">成本价</th>
                            <th className="text-right px-4 py-2">现价</th>
                            <th className="text-right px-4 py-2">数量</th>
                            <th className="text-right px-4 py-2">市值</th>
                            <th className="text-right px-4 py-2">盈亏</th>
                            <th className="text-right px-4 py-2">盈亏率</th>
                          </tr>
                        </thead>
                        <tbody>
                          {portfolio.positions.map((p) => (
                            <tr key={p.stock_code} className="border-b last:border-b-0">
                              <td className="px-4 py-2">
                                <div className="font-medium text-gray-900">{p.stock_name || p.stock_code}</div>
                                <div className="text-xs text-gray-400 font-mono">{p.stock_code}</div>
                              </td>
                              <td className="px-4 py-2 text-right font-mono">{formatPrice(p.cost_price)}</td>
                              <td className="px-4 py-2 text-right font-mono">{formatPrice(p.current_price)}</td>
                              <td className="px-4 py-2 text-right font-mono">{p.volume || 0}</td>
                              <td className="px-4 py-2 text-right font-mono">{formatMoneyYuan(p.market_value)}</td>
                              <td className={`px-4 py-2 text-right font-mono ${changeColor(p.profit)}`}>{formatMoneyYuan(p.profit)}</td>
                              <td className={`px-4 py-2 text-right font-mono ${changeColor(p.profit_percent)}`}>{formatPct(p.profit_percent)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 持仓录入 */}
	            <div className="mt-6 bg-white rounded-xl border border-[color:var(--border-color)] p-4">
	              <div className="flex items-center justify-between gap-3">
	                <div className="font-medium text-gray-900">持仓录入</div>
	                <div className="text-xs text-gray-500">成本价{'>'}0 且 持仓数量{'>'}0 才会计入组合分析</div>
	              </div>

              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">股票</label>
                  <select
                    value={positionEditor.code}
                    onChange={(e) => setPositionEditorCode(e.target.value)}
                    className="input"
                  >
                    <option value="">请选择</option>
                    {stocks.map((s) => (
                      <option key={s.stock_code} value={s.stock_code}>
                        {s.stock_name || s.stock_code}（{s.stock_code}）
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">成本价</label>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="0.01"
                    value={positionEditor.costPrice}
                    onChange={(e) => setPositionEditor((prev) => ({ ...prev, costPrice: e.target.value }))}
                    placeholder="例如 12.34"
                    className="input"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">持仓数量</label>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={0}
                    step="1"
                    value={positionEditor.volume}
                    onChange={(e) => setPositionEditor((prev) => ({ ...prev, volume: e.target.value }))}
                    placeholder="例如 100"
                    className="input"
                  />
                </div>
              </div>

              <div className="mt-4 flex items-center justify-end gap-2">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={positionSaving}
                  onClick={() => setPositionEditor((prev) => ({ ...prev, costPrice: "", volume: "" }))}
                >
                  清空
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={positionSaving || portfolioLoading}
                  onClick={savePosition}
                >
                  {positionSaving ? "保存中..." : "保存"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!removeStockConfirm}
        title="确认移除该股票？"
        description={
          removeStockConfirm
            ? `${removeStockConfirm.name ? `${removeStockConfirm.name}（${removeStockConfirm.code}）` : removeStockConfirm.code} 将从自选股移除。`
            : undefined
        }
        confirmText="移除"
        cancelText="取消"
        variant="danger"
        onCancel={() => setRemoveStockConfirm(null)}
        onConfirm={() => {
          const code = removeStockConfirm?.code;
          const name = removeStockConfirm?.name;
          setRemoveStockConfirm(null);
          if (!code) return;
          handleRemove(code, name);
          if (selectedStock === code) setSelectedStock(null);
        }}
      />

      <ConfirmDialog
        open={!!deleteGroupConfirm}
        title="确认删除该分组？"
        description={deleteGroupConfirm ? `分组「${deleteGroupConfirm.name}」将被删除，且其分组关系将移除。` : undefined}
        confirmText="删除"
        cancelText="取消"
        variant="danger"
        onCancel={() => setDeleteGroupConfirm(null)}
        onConfirm={() => {
          const id = deleteGroupConfirm?.id;
          const name = deleteGroupConfirm?.name;
          setDeleteGroupConfirm(null);
          if (!id) return;
          handleDeleteGroup(id, name);
        }}
      />
    </div>
  );
}
