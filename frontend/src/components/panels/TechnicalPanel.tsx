"use client";

import { useState } from "react";
import api from "@/lib/api";

export default function TechnicalPanel() {
  const [code, setCode] = useState("");
  const [analysis, setAnalysis] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleAnalyze = async () => {
    if (!code.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.getTechnicalAnalysis(code);
      setAnalysis(result);
    } catch (e: any) {
      setError(e.message || "分析失败");
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  const signalColors: Record<string, string> = {
    strong_buy: "bg-red-600", buy: "bg-red-500", weak_buy: "bg-red-300",
    hold: "bg-gray-400", weak_sell: "bg-green-300", sell: "bg-green-500", strong_sell: "bg-green-600",
  };

  const safeNumber = (v: any, decimals: number = 2) => typeof v === "number" ? v.toFixed(decimals) : "-";

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">技术分析</h1>

      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
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

          {/* 评分仪表盘 */}
          <div className="grid grid-cols-5 gap-4 mb-6">
            <div className="col-span-2 bg-white rounded-xl p-6 shadow-sm text-center">
              <div className="text-6xl font-bold mb-2">{analysis.score ?? "-"}</div>
              <div className="text-gray-500">综合评分</div>
              <div className={`mt-4 inline-block px-4 py-2 rounded-full text-white text-sm font-medium ${signalColors[analysis.buy_signal] || "bg-gray-400"}`}>
                {analysis.buy_signal === "strong_buy" ? "强烈买入" :
                  analysis.buy_signal === "buy" ? "买入" :
                  analysis.buy_signal === "weak_buy" ? "弱买入" :
                  analysis.buy_signal === "hold" ? "观望" :
                  analysis.buy_signal === "weak_sell" ? "弱卖出" :
                  analysis.buy_signal === "sell" ? "卖出" : "强烈卖出"}
              </div>
            </div>
            <div className="col-span-3 bg-white rounded-xl p-6 shadow-sm">
              <h3 className="font-medium mb-4">评分明细</h3>
              <div className="space-y-3">
                {analysis.score_details && Object.entries(analysis.score_details).map(([key, value]: [string, any]) => (
                  <div key={key} className="flex items-center gap-3">
                    <span className="w-16 text-sm text-gray-500">{
                      key === "trend" ? "趋势" :
                      key === "bias" ? "乖离率" :
                      key === "volume" ? "成交量" :
                      key === "support" ? "支撑位" :
                      key === "macd" ? "MACD" : "RSI"
                    }</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2">
                      <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${(value / (key === "trend" ? 30 : key === "bias" ? 20 : key === "macd" || key === "volume" ? 15 : 10)) * 100}%` }} />
                    </div>
                    <span className="w-8 text-sm text-right">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 指标卡片 */}
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

          {/* 分析摘要 */}
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
