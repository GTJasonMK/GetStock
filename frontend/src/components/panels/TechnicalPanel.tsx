"use client";

import { useMemo, useState } from "react";
import api from "@/lib/api";

type BuySignal = "strong_buy" | "buy" | "weak_buy" | "hold" | "weak_sell" | "sell" | "strong_sell";
type ScoreKey = "trend" | "bias" | "volume" | "support" | "macd" | "rsi";
type ScoreDetails = Partial<Record<ScoreKey, number>>;

type TrendMetrics = {
  status?: string;
  ma_5?: number;
  ma_10?: number;
  ma_20?: number;
};

type MacdMetrics = {
  dif?: number;
  dea?: number;
  macd?: number;
  signal?: string;
};

type RsiMetrics = {
  rsi_6?: number;
  rsi_12?: number;
  rsi_24?: number;
  signal?: string;
};

type TechnicalAnalysis = {
  name?: string;
  code?: string;
  score?: number;
  buy_signal?: BuySignal;
  score_details?: ScoreDetails;
  trend?: TrendMetrics;
  macd?: MacdMetrics;
  rsi?: RsiMetrics;
  summary?: string;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const toNumber = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

const toText = (value: unknown): string | undefined =>
  typeof value === "string" && value.trim() ? value : undefined;

const normalizeScoreDetails = (value: unknown): ScoreDetails | undefined => {
  if (!isRecord(value)) return undefined;
  return {
    trend: toNumber(value.trend),
    bias: toNumber(value.bias),
    volume: toNumber(value.volume),
    support: toNumber(value.support),
    macd: toNumber(value.macd),
    rsi: toNumber(value.rsi),
  };
};

const normalizeTrend = (value: unknown): TrendMetrics | undefined => {
  if (!isRecord(value)) return undefined;
  return {
    status: toText(value.status),
    ma_5: toNumber(value.ma_5),
    ma_10: toNumber(value.ma_10),
    ma_20: toNumber(value.ma_20),
  };
};

const normalizeMacd = (value: unknown): MacdMetrics | undefined => {
  if (!isRecord(value)) return undefined;
  return {
    dif: toNumber(value.dif),
    dea: toNumber(value.dea),
    macd: toNumber(value.macd),
    signal: toText(value.signal),
  };
};

const normalizeRsi = (value: unknown): RsiMetrics | undefined => {
  if (!isRecord(value)) return undefined;
  return {
    rsi_6: toNumber(value.rsi_6),
    rsi_12: toNumber(value.rsi_12),
    rsi_24: toNumber(value.rsi_24),
    signal: toText(value.signal),
  };
};

const normalizeAnalysis = (value: unknown): TechnicalAnalysis | null => {
  if (!isRecord(value)) return null;
  return {
    name: toText(value.name),
    code: toText(value.code),
    score: toNumber(value.score),
    buy_signal: toText(value.buy_signal) as BuySignal | undefined,
    score_details: normalizeScoreDetails(value.score_details),
    trend: normalizeTrend(value.trend),
    macd: normalizeMacd(value.macd),
    rsi: normalizeRsi(value.rsi),
    summary: toText(value.summary),
  };
};

const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error && error.message) return error.message;
  if (isRecord(error) && typeof error.message === "string") return error.message;
  return "分析失败";
};

const signalColors: Record<BuySignal, string> = {
  strong_buy: "bg-red-600",
  buy: "bg-red-500",
  weak_buy: "bg-red-300",
  hold: "bg-gray-400",
  weak_sell: "bg-green-300",
  sell: "bg-green-500",
  strong_sell: "bg-green-600",
};

const signalLabel = (signal?: BuySignal) => {
  if (signal === "strong_buy") return "强烈买入";
  if (signal === "buy") return "买入";
  if (signal === "weak_buy") return "弱买入";
  if (signal === "hold") return "观望";
  if (signal === "weak_sell") return "弱卖出";
  if (signal === "sell") return "卖出";
  return "强烈卖出";
};

const scoreLabel = (key: string) => {
  if (key === "trend") return "趋势";
  if (key === "bias") return "乖离率";
  if (key === "volume") return "成交量";
  if (key === "support") return "支撑位";
  if (key === "macd") return "MACD";
  return "RSI";
};

const scoreMax = (key: string) => {
  if (key === "trend") return 30;
  if (key === "bias") return 20;
  if (key === "macd" || key === "volume") return 15;
  return 10;
};

const safeNumber = (value: unknown, decimals = 2) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(decimals) : "-";

export default function TechnicalPanel() {
  const [code, setCode] = useState("");
  const [analysis, setAnalysis] = useState<TechnicalAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const scoreEntries = useMemo(
    () =>
      (analysis?.score_details
        ? Object.entries(analysis.score_details).flatMap(([key, value]) =>
            typeof value === "number" ? ([[key, value]] as [string, number][]) : []
          )
        : []),
    [analysis]
  );

  const handleAnalyze = async () => {
    const normalizedCode = code.trim();
    if (!normalizedCode) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.getTechnicalAnalysis(normalizedCode);
      setAnalysis(normalizeAnalysis(result));
    } catch (errorObject: unknown) {
      setError(getErrorMessage(errorObject));
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">技术分析</h1>

      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && handleAnalyze()}
          placeholder="输入股票代码 (如 sh600519)"
          className="flex-1 max-w-md px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button type="button" onClick={handleAnalyze} disabled={loading} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
          {loading ? "分析中..." : "开始分析"}
        </button>
      </div>

      {error && <div className="mb-4 p-4 bg-red-50 text-red-600 rounded-lg">{error}</div>}

      {analysis && (
        <div>
          <div className="flex items-center gap-4 mb-6">
            <h2 className="text-xl font-bold">{analysis.name || code}</h2>
            <span className="text-gray-500">{analysis.code || code}</span>
          </div>

          <div className="grid grid-cols-5 gap-4 mb-6">
            <div className="col-span-2 bg-white rounded-xl p-6 shadow-sm text-center">
              <div className="text-6xl font-bold mb-2">{analysis.score ?? "-"}</div>
              <div className="text-gray-500">综合评分</div>
              <div
                className={`mt-4 inline-block px-4 py-2 rounded-full text-white text-sm font-medium ${
                  analysis.buy_signal ? signalColors[analysis.buy_signal] : "bg-gray-400"
                }`}
              >
                {signalLabel(analysis.buy_signal)}
              </div>
            </div>
            <div className="col-span-3 bg-white rounded-xl p-6 shadow-sm">
              <h3 className="font-medium mb-4">评分明细</h3>
              <div className="space-y-3">
                {scoreEntries.map(([key, value]) => (
                  <div key={key} className="flex items-center gap-3">
                    <span className="w-16 text-sm text-gray-500">{scoreLabel(key)}</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${(value / scoreMax(key)) * 100}%` }} />
                    </div>
                    <span className="w-8 text-sm text-right">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-6">
            {analysis.trend && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">趋势分析</h3>
                <div className="text-sm space-y-2">
                  <div className="flex justify-between"><span className="text-gray-500">趋势状态</span><span className="font-medium">{analysis.trend.status || "-"}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">MA5</span><span>{safeNumber(analysis.trend.ma_5)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">MA10</span><span>{safeNumber(analysis.trend.ma_10)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">MA20</span><span>{safeNumber(analysis.trend.ma_20)}</span></div>
                </div>
              </div>
            )}
            {analysis.macd && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">MACD</h3>
                <div className="text-sm space-y-2">
                  <div className="flex justify-between"><span className="text-gray-500">DIF</span><span>{safeNumber(analysis.macd.dif, 3)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">DEA</span><span>{safeNumber(analysis.macd.dea, 3)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">MACD</span><span>{safeNumber(analysis.macd.macd, 3)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">信号</span><span className="font-medium">{analysis.macd.signal || "-"}</span></div>
                </div>
              </div>
            )}
            {analysis.rsi && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">RSI</h3>
                <div className="text-sm space-y-2">
                  <div className="flex justify-between"><span className="text-gray-500">RSI6</span><span>{safeNumber(analysis.rsi.rsi_6, 1)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">RSI12</span><span>{safeNumber(analysis.rsi.rsi_12, 1)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">RSI24</span><span>{safeNumber(analysis.rsi.rsi_24, 1)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">信号</span><span className="font-medium">{analysis.rsi.signal || "-"}</span></div>
                </div>
              </div>
            )}
          </div>

          {analysis.summary && (
            <div className="bg-white rounded-xl p-4 shadow-sm">
              <h3 className="font-medium mb-2">分析摘要</h3>
              <p className="text-gray-600 leading-relaxed">{analysis.summary}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
