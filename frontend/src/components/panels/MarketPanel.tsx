"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import BoardMoneyHeatmap from "@/components/charts/BoardMoneyHeatmap";
import type { BoardMoneyItem } from "@/components/charts/BoardMoneyHeatmap";
import NorthFlowChart from "@/components/charts/NorthFlowChart";
import MarketTreemap from "@/components/charts/MarketTreemap";
import type { MarketTreemapItem } from "@/components/charts/MarketTreemap";

type MarketTab =
  | "overview"
  | "industry"
  | "concept"
  | "money"
  | "stockMoney"
  | "longTiger"
  | "limit"
  | "north"
  | "heatmap"
  | "marketMap"
  | "rank"
  | "portfolio";

export default function MarketPanel() {
  const [tab, setTab] = useState<MarketTab>("overview");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [moneySubTab, setMoneySubTab] = useState<"industry" | "concept">("industry");
  const [heatmapCategory, setHeatmapCategory] = useState<"industry" | "concept">("industry");
  const [stockMoneySortBy, setStockMoneySortBy] = useState("zjlr");
  const [longTigerDateInput, setLongTigerDateInput] = useState("");
  const [longTigerQueryDate, setLongTigerQueryDate] = useState<string | undefined>(undefined);
  const [northDays, setNorthDays] = useState(30);
  const [marketMapSortBy, setMarketMapSortBy] = useState<"market_cap" | "amount">("market_cap");

  useEffect(() => {
    // 先用缓存快速回填，避免页面切换/返回时出现“整页白屏等待”
    try {
      let endpoint = "";
      if (tab === "overview") endpoint = `/market/overview`;
      else if (tab === "industry") endpoint = `/market/industry-rank?sort_by=change_percent&order=desc&limit=20`;
      else if (tab === "concept") endpoint = `/market/concept-rank?sort_by=change_percent&order=desc&limit=20`;
      else if (tab === "money") endpoint = `/market/industry-money-flow?category=${moneySubTab === "industry" ? "hangye" : "gainian"}&sort_by=main_inflow`;
      else if (tab === "stockMoney") endpoint = `/market/stock-money-rank?sort_by=${stockMoneySortBy}&limit=50`;
      else if (tab === "longTiger") endpoint = longTigerQueryDate ? `/market/long-tiger?trade_date=${longTigerQueryDate}` : `/market/long-tiger`;
      else if (tab === "limit") endpoint = `/market/limit-stats`;
      else if (tab === "north") endpoint = `/market/north-flow?days=${northDays}`;
      else if (tab === "heatmap") endpoint = `/market/industry-money-flow?category=${heatmapCategory === "industry" ? "hangye" : "gainian"}&sort_by=main_inflow`;
      else if (tab === "marketMap") endpoint = `/stock/rank?sort_by=${marketMapSortBy}&order=desc&limit=200&market=all`;
      else if (tab === "rank") endpoint = `/stock/rank?sort_by=change_percent&order=desc&limit=50&market=all`;
      else if (tab === "portfolio") endpoint = `/stock/portfolio/analysis`;

      if (endpoint) {
        const cached = api.peekCache<any>(endpoint);
        if (cached != null) setData(cached);
      }
    } catch {
      // ignore
    }

    setLoading(true);
    setError(null);
    const fetchData = async () => {
      try {
        let result;
        if (tab === "overview") result = await api.getMarketOverview();
        else if (tab === "industry") result = await api.getIndustryRank();
        else if (tab === "concept") result = await api.getConceptRank();
        else if (tab === "money") result = await api.getIndustryMoneyFlow(moneySubTab === "industry" ? "hangye" : "gainian");
        else if (tab === "stockMoney") result = await api.getStockMoneyRank(stockMoneySortBy);
        else if (tab === "longTiger") result = await api.getLongTiger(longTigerQueryDate);
        else if (tab === "limit") result = await api.getLimitStats();
        else if (tab === "north") result = await api.getNorthFlow(northDays);
        else if (tab === "heatmap") result = await api.getIndustryMoneyFlow(heatmapCategory === "industry" ? "hangye" : "gainian");
        else if (tab === "marketMap") result = await api.getStockRank(marketMapSortBy, "desc", 200);
        else if (tab === "rank") result = await api.getStockRank("change_percent", "desc", 50);
        else if (tab === "portfolio") result = await api.getPortfolioAnalysis();
        setData(result);
      } catch (e: any) {
        setData(null);
        const msg = e instanceof Error ? e.message : String(e || "获取数据失败");
        setError(msg);
      }
      setLoading(false);
    };
    fetchData();
  }, [tab, moneySubTab, heatmapCategory, stockMoneySortBy, longTigerQueryDate, northDays, marketMapSortBy, reloadToken]);

  // 自动把“当前展示的交易日”填充到输入框（仅在输入框为空时）
  useEffect(() => {
    if (tab !== "longTiger") return;
    const resolved = data?.trade_date;
    if (typeof resolved !== "string" || !resolved) return;
    if (longTigerDateInput) return;
    setLongTigerDateInput(resolved);
  }, [tab, data?.trade_date, longTigerDateInput]);

  const formatChange = (v: number | null) => v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const changeColor = (v: number | null) => v == null ? "" : v > 0 ? "text-red-600" : v < 0 ? "text-green-600" : "";

  // 金额（元）格式化：用于成交额/北向资金等“元”口径字段
  const formatMoneyYuan = (v: number | null) => {
    if (v == null) return "-";
    if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + "亿";
    if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + "万";
    return v.toFixed(2);
  };

  // 金额（万）格式化：用于龙虎榜/主力净流入等“万”口径字段（万 -> 亿 用 1e4）
  const formatMoneyWan = (v: number | null) => {
    if (v == null) return "-";
    if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + "亿";
    return v.toFixed(2) + "万";
  };

  // 亿元口径（MarketOverview total_amount/north_flow）
  const formatYi = (v: number | null | undefined) => {
    if (v == null) return "-";
    return `${v.toFixed(2)}亿`;
  };

  // 兼容后端不同返回形态：有些接口返回数组，有些返回 {items: []}
  const toList = (v: any) => (Array.isArray(v) ? v : Array.isArray(v?.items) ? v.items : []);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">市场数据</h1>

      {/* Tab */}
      <div className="tablist mb-6">
        {[
          { key: "overview", label: "概览" },
          { key: "industry", label: "行业排名" },
          { key: "concept", label: "概念板块" },
          { key: "money", label: "行业资金" },
          { key: "stockMoney", label: "个股资金" },
          { key: "longTiger", label: "龙虎榜" },
          { key: "limit", label: "涨跌停" },
          { key: "north", label: "北向资金" },
          { key: "heatmap", label: "板块热力图" },
          { key: "marketMap", label: "市场热力图" },
          { key: "rank", label: "股票排行" },
          { key: "portfolio", label: "持仓分析" },
        ].map((t) => (
          <button
            type="button"
            key={t.key}
            onClick={() => setTab(t.key as MarketTab)}
            className={`tab ${tab === t.key ? "tab-active" : "tab-inactive"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          {loading && !!data && (
            <div className="px-4 py-2 border-b bg-[var(--bg-surface-muted)] text-xs text-[var(--text-muted)] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
                正在更新数据…
              </div>
              <button
                type="button"
                onClick={() => setReloadToken((x) => x + 1)}
                className="px-2 py-1 rounded-md bg-white border border-[color:var(--border-color)] hover:bg-[var(--bg-surface)] transition-colors"
              >
                手动刷新
              </button>
            </div>
          )}
          {!!error && (
            <div className="px-4 py-3 border-b bg-amber-50 text-amber-800 flex items-start justify-between gap-4">
              <div className="text-sm leading-5">
                <div className="font-medium">数据获取失败</div>
                <div className="mt-1 break-all">{error}</div>
              </div>
              <button
                type="button"
                onClick={() => setReloadToken((x) => x + 1)}
                className="shrink-0 px-3 py-1.5 text-sm rounded-md bg-amber-600 text-white hover:bg-amber-700 transition-colors"
              >
                重试
              </button>
            </div>
          )}

          {/* 市场概览 */}
          {tab === "overview" && data && (
            <div className="p-6 space-y-6">
              {!data.available && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  <div className="font-medium">部分数据不可用</div>
                  <div className="mt-1 break-all">{data.reason || "数据源异常，请稍后重试"}</div>
                </div>
              )}

              {/* 指数 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {(data.indices || []).map((idx: any) => (
                  <div key={idx.code} className="p-4 bg-gray-50 rounded-xl">
                    <div className="flex items-center justify-between">
                      <div className="font-medium">{idx.name}</div>
                      <div className="text-xs text-gray-400">{idx.update_time || data.date}</div>
                    </div>
                    <div className="mt-2 flex items-end justify-between">
                      <div className="text-2xl font-bold font-mono">{Number(idx.current || 0).toFixed(2)}</div>
                      <div className={`text-sm font-mono ${changeColor(idx.change_percent)}`}>
                        {formatChange(idx.change_percent ?? null)} ({Number(idx.change_amount || 0).toFixed(2)})
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* 市场宽度 */}
              <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                {[
                  { label: "上涨", value: data.up_count ?? 0, cls: "text-red-600" },
                  { label: "下跌", value: data.down_count ?? 0, cls: "text-green-600" },
                  { label: "平盘", value: data.flat_count ?? 0, cls: "text-gray-600" },
                  { label: "涨停", value: data.limit_up_count ?? 0, cls: "text-red-600" },
                  { label: "跌停", value: data.limit_down_count ?? 0, cls: "text-green-600" },
                  { label: "成交额", value: formatYi(data.total_amount), cls: "text-gray-900" },
                ].map((kpi) => (
                  <div key={kpi.label} className="text-center p-4 bg-gray-50 rounded-xl">
                    <div className={`text-2xl font-bold ${kpi.cls}`}>{kpi.value}</div>
                    <div className="text-gray-500 mt-1 text-sm">{kpi.label}</div>
                  </div>
                ))}
              </div>

              {/* 北向资金（可选） */}
              {data.north_flow != null && (
                <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                  <div className="text-gray-600">北向资金净买额</div>
                  <div className={`text-xl font-bold font-mono ${changeColor(data.north_flow)}`}>
                    {data.north_flow > 0 ? "+" : ""}{formatYi(data.north_flow)}
                  </div>
                </div>
              )}

              {/* 板块榜 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-white border rounded-xl">
                  <div className="font-medium mb-3 text-gray-800">领涨板块</div>
                  {(data.top_sectors || []).length > 0 ? (
                    <div className="space-y-2">
                      {(data.top_sectors || []).map((s: any) => (
                        <div key={s.code || s.name} className="flex items-center justify-between">
                          <div className="text-gray-700">{s.name}</div>
                          <div className={`font-mono ${changeColor(s.change_pct)}`}>{formatChange(s.change_pct ?? null)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-400">暂无数据</div>
                  )}
                </div>
                <div className="p-4 bg-white border rounded-xl">
                  <div className="font-medium mb-3 text-gray-800">领跌板块</div>
                  {(data.bottom_sectors || []).length > 0 ? (
                    <div className="space-y-2">
                      {(data.bottom_sectors || []).map((s: any) => (
                        <div key={s.code || s.name} className="flex items-center justify-between">
                          <div className="text-gray-700">{s.name}</div>
                          <div className={`font-mono ${changeColor(s.change_pct)}`}>{formatChange(s.change_pct ?? null)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-400">暂无数据</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 行业/概念排名 */}
          {(tab === "industry" || tab === "concept") && (
            data?.items?.length > 0 ? (
              <table className="w-full">
                <thead className="bg-gray-50 text-sm text-gray-500">
                  <tr>
                    <th className="px-4 py-3 text-left">名称</th>
                    <th className="px-4 py-3 text-right">涨跌幅</th>
                    <th className="px-4 py-3 text-right">换手率</th>
                    <th className="px-4 py-3 text-left">领涨股</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item: any, i: number) => (
                    <tr key={i} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{item.bk_name}</td>
                      <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                      <td className="px-4 py-3 text-right text-gray-500">
                        {typeof item.turnover === "number" && Number.isFinite(item.turnover) && item.turnover > 0
                          ? `${item.turnover.toFixed(2)}%`
                          : "-"}
                      </td>
                      <td className="px-4 py-3 text-gray-500">{item.leader_stock_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-8 text-center text-gray-400">暂无数据</div>
            )
          )}

          {/* 行业/概念资金流向 */}
          {tab === "money" && (
            <div>
              <div className="px-4 py-3 border-b flex gap-2">
                {[
                  { key: "industry", label: "行业" },
                  { key: "concept", label: "概念" },
                ].map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setMoneySubTab(t.key as "industry" | "concept")}
                    className={`px-3 py-1 text-sm rounded-md transition-colors duration-200 cursor-pointer ${
                      moneySubTab === t.key
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--bg-surface-muted)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {toList(data).length > 0 ? (
                <table className="w-full">
                  <thead className="bg-gray-50 text-sm text-gray-500">
                    <tr>
                      <th className="px-4 py-3 text-left">名称</th>
                      <th className="px-4 py-3 text-right">涨跌幅</th>
                      <th className="px-4 py-3 text-right">主力净流入</th>
                      <th className="px-4 py-3 text-right">净流入占比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {toList(data).map((item: any, i: number) => (
                      <tr key={i} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium">{item.name}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.main_net_inflow)}`}>{formatMoneyYuan(item.main_net_inflow)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.main_net_inflow_percent)}`}>{item.main_net_inflow_percent?.toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-8 text-center text-gray-400">
                  暂无数据
                  <div className="text-xs text-gray-400 mt-2">可能原因：数据源限流/网络不稳定。可稍后重试或切换其他 Tab。</div>
                </div>
              )}
            </div>
          )}

          {/* 个股资金流向 */}
          {tab === "stockMoney" && (
            <div>
              <div className="px-4 py-3 border-b flex gap-2">
                {[
                  { key: "zjlr", label: "主力净流入" },
                  { key: "trade", label: "现价" },
                  { key: "changeratio", label: "涨跌幅" },
                ].map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setStockMoneySortBy(t.key)}
                    className={`px-3 py-1 text-sm rounded-md transition-colors duration-200 cursor-pointer ${
                      stockMoneySortBy === t.key
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--bg-surface-muted)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {toList(data).length > 0 ? (
                <table className="w-full">
                  <thead className="bg-gray-50 text-sm text-gray-500">
                    <tr>
                      <th className="px-4 py-3 text-left">代码</th>
                      <th className="px-4 py-3 text-left">名称</th>
                      <th className="px-4 py-3 text-right">现价</th>
                      <th className="px-4 py-3 text-right">涨跌幅</th>
                      <th className="px-4 py-3 text-right">主力净流入</th>
                      <th className="px-4 py-3 text-right">净流入占比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {toList(data).map((item: any, i: number) => (
                      <tr key={i} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-3 text-gray-500 font-mono text-sm">{item.stock_code}</td>
                        <td className="px-4 py-3 font-medium">{item.stock_name}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{item.current_price?.toFixed(2) || "-"}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.main_net_inflow)}`}>{formatMoneyWan(item.main_net_inflow)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.main_net_inflow_percent)}`}>{item.main_net_inflow_percent?.toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-8 text-center text-gray-400">
                  暂无数据
                  <div className="text-xs text-gray-400 mt-2">提示：该榜单依赖外部行情源，若持续为空请稍后重试。</div>
                </div>
              )}
            </div>
          )}

          {/* 龙虎榜 */}
          {tab === "longTiger" && (
            <div>
              <div className="px-4 py-3 border-b bg-gray-50 flex flex-wrap items-center gap-3">
                <div className="text-sm text-gray-600">交易日期</div>
                <input
                  type="date"
                  value={longTigerDateInput}
                  onChange={(e) => setLongTigerDateInput(e.target.value)}
                  className="input w-44"
                  aria-label="龙虎榜交易日期"
                />
                <button
                  type="button"
                  onClick={() => {
                    const value = (longTigerDateInput || "").trim();
                    setLongTigerQueryDate(value || undefined);
                    setReloadToken((x) => x + 1);
                  }}
                  className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90 transition-colors"
                >
                  查询
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setLongTigerQueryDate(undefined);
                    setLongTigerDateInput("");
                    setReloadToken((x) => x + 1);
                  }}
                  className="px-3 py-1.5 text-sm rounded-md bg-white border border-[color:var(--border-color)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-muted)] transition-colors"
                >
                  自动
                </button>
                {typeof data?.trade_date === "string" && data.trade_date && (
                  <div className="text-xs text-gray-400">当前展示：{data.trade_date}</div>
                )}
              </div>

              {data?.items?.length > 0 ? (
                <table className="w-full">
                  <thead className="bg-gray-50 text-sm text-gray-500">
                    <tr>
                      <th className="px-4 py-3 text-left">代码</th>
                      <th className="px-4 py-3 text-left">名称</th>
                      <th className="px-4 py-3 text-right">涨跌幅</th>
                      <th className="px-4 py-3 text-right">龙虎榜净买额</th>
                      <th className="px-4 py-3 text-right">龙虎榜买入额</th>
                      <th className="px-4 py-3 text-right">龙虎榜卖出额</th>
                      <th className="px-4 py-3 text-left">上榜原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item: any, i: number) => (
                      <tr key={i} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-3 text-gray-500 font-mono text-sm">{item.stock_code}</td>
                        <td className="px-4 py-3 font-medium">{item.stock_name}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.net_buy_amount)}`}>{formatMoneyWan(item.net_buy_amount)}</td>
                        <td className="px-4 py-3 text-right text-red-500">{formatMoneyWan(item.buy_amount)}</td>
                        <td className="px-4 py-3 text-right text-green-500">{formatMoneyWan(item.sell_amount)}</td>
                        <td className="px-4 py-3 text-gray-500 text-sm">{item.reason || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-8 text-center text-gray-400">
                  暂无龙虎榜数据{typeof data?.trade_date === "string" && data.trade_date ? `（${data.trade_date}）` : ""}
                </div>
              )}
            </div>
          )}

          {/* 涨跌停 */}
          {tab === "limit" && data && (
            <div className="p-6">
              <div className="grid grid-cols-2 gap-6 mb-6">
                <div className="text-center p-6 bg-red-50 rounded-xl">
                  <div className="text-4xl font-bold text-red-600">{data.limit_up_count || 0}</div>
                  <div className="text-gray-600 mt-2">涨停</div>
                </div>
                <div className="text-center p-6 bg-green-50 rounded-xl">
                  <div className="text-4xl font-bold text-green-600">{data.limit_down_count || 0}</div>
                  <div className="text-gray-600 mt-2">跌停</div>
                </div>
              </div>
              {data.limit_up_stocks?.length > 0 && (
                <div className="mb-4">
                  <h3 className="font-medium text-red-600 mb-2">涨停股票</h3>
                  <div className="flex flex-wrap gap-2">
                    {data.limit_up_stocks.slice(0, 20).map((s: any, i: number) => (
                      <span key={i} className="px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm">{s.stock_name}</span>
                    ))}
                  </div>
                </div>
              )}
              {data.limit_down_stocks?.length > 0 && (
                <div>
                  <h3 className="font-medium text-green-600 mb-2">跌停股票</h3>
                  <div className="flex flex-wrap gap-2">
                    {data.limit_down_stocks.slice(0, 20).map((s: any, i: number) => (
                      <span key={i} className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm">{s.stock_name}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 北向资金 */}
          {tab === "north" && data && (
            <div className="p-6">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                <div className="text-sm text-gray-600">
                  近
                  <select
                    className="mx-2 px-2 py-1 border rounded-md bg-white text-sm"
                    value={northDays}
                    onChange={(e) => setNorthDays(Number(e.target.value))}
                    title="选择回溯天数"
                  >
                    {[10, 30, 60, 90].map((d) => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                  日走势
                </div>
                <button type="button" onClick={() => setReloadToken((x) => x + 1)} className="btn btn-secondary text-sm px-3 py-1.5">
                  刷新
                </button>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                <div className="text-sm text-gray-600">
                  口径：{data.metric || "成交净买额"}（{data.unit || "元"}）
                  {!!data.asof_date && <span className="ml-2 text-gray-400">数据日期：{data.asof_date}</span>}
                </div>
                <div className="text-xs text-gray-400">来源：{data.source || "-"}</div>
              </div>

              {Array.isArray(data.history) && data.history.length > 0 && (
                <div className="mb-6">
                  <NorthFlowChart metric={data.metric} unit={data.unit} history={data.history} />
                </div>
              )}

              {data.current && (
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="text-center p-4 bg-gray-50 rounded-xl">
                    <div className={`text-2xl font-bold ${changeColor(data.current.total_inflow)}`}>{formatMoneyYuan(data.current.total_inflow)}</div>
                    <div className="text-gray-500 mt-1">当日{data.metric || "净买额"}</div>
                  </div>
                  <div className="text-center p-4 bg-gray-50 rounded-xl">
                    <div className={`text-2xl font-bold ${changeColor(data.current.sh_inflow)}`}>{formatMoneyYuan(data.current.sh_inflow)}</div>
                    <div className="text-gray-500 mt-1">沪股通</div>
                  </div>
                  <div className="text-center p-4 bg-gray-50 rounded-xl">
                    <div className={`text-2xl font-bold ${changeColor(data.current.sz_inflow)}`}>{formatMoneyYuan(data.current.sz_inflow)}</div>
                    <div className="text-gray-500 mt-1">深股通</div>
                  </div>
                </div>
              )}
              {data.history?.length > 0 && (
                <table className="w-full">
                  <thead className="bg-gray-50 text-sm text-gray-500">
                    <tr>
                      <th className="px-4 py-3 text-left">日期</th>
                      <th className="px-4 py-3 text-right">沪股通</th>
                      <th className="px-4 py-3 text-right">深股通</th>
                      <th className="px-4 py-3 text-right">合计</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.slice(0, 10).map((item: any, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-3">{item.date}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.sh_inflow)}`}>{formatMoneyYuan(item.sh_inflow)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.sz_inflow)}`}>{formatMoneyYuan(item.sz_inflow)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.total_inflow)}`}>{formatMoneyYuan(item.total_inflow)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {!data.current && (!data.history || data.history.length === 0) && (
                <div className="text-center py-8 text-gray-400">暂无北向资金数据</div>
              )}
            </div>
          )}

          {/* 市场热力图（按行业） */}
          {tab === "marketMap" && (
            <div className="p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm text-gray-600">
                  面积口径：
                  <button
                    type="button"
                    onClick={() => setMarketMapSortBy("market_cap")}
                    className={`ml-2 px-3 py-1 text-sm rounded-md transition-colors duration-200 cursor-pointer ${
                      marketMapSortBy === "market_cap"
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--bg-surface-muted)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    总市值
                  </button>
                  <button
                    type="button"
                    onClick={() => setMarketMapSortBy("amount")}
                    className={`ml-2 px-3 py-1 text-sm rounded-md transition-colors duration-200 cursor-pointer ${
                      marketMapSortBy === "amount"
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--bg-surface-muted)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    成交额
                  </button>
                </div>
                <button type="button" onClick={() => setReloadToken((x) => x + 1)} className="btn btn-secondary text-sm px-3 py-1.5">
                  刷新
                </button>
              </div>

              <MarketTreemap
                title="市场热力图（按行业）"
                items={toList(data) as MarketTreemapItem[]}
                sizeBy={marketMapSortBy === "amount" ? "amount" : "total_market_cap"}
                height={620}
              />
            </div>
          )}

          {/* 热力图 */}
          {tab === "heatmap" && (
            <div className="p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex gap-2">
                  {[
                    { key: "industry", label: "行业" },
                    { key: "concept", label: "概念" },
                  ].map((t) => (
                    <button
                      key={t.key}
                      type="button"
                      onClick={() => setHeatmapCategory(t.key as "industry" | "concept")}
                      className={`px-3 py-1 text-sm rounded-md transition-colors duration-200 cursor-pointer ${
                        heatmapCategory === t.key
                          ? "bg-[var(--accent)] text-white"
                          : "bg-[var(--bg-surface-muted)] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <button type="button" onClick={() => setReloadToken((x) => x + 1)} className="btn btn-secondary text-sm px-3 py-1.5">
                  刷新
                </button>
              </div>

              {toList(data).length > 0 ? (
                <BoardMoneyHeatmap
                  title={`${heatmapCategory === "industry" ? "行业" : "概念"}资金热力图`}
                  items={toList(data) as BoardMoneyItem[]}
                />
              ) : (
                <div className="text-center py-10 text-gray-400">暂无热力图数据</div>
              )}

              {toList(data).length > 0 && (
                <div className="bg-white rounded-xl shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b text-sm text-gray-600">
                    热力图数据明细（Top {Math.min(50, toList(data).length)}）
                  </div>
                  <table className="w-full">
                    <thead className="bg-gray-50 text-sm text-gray-500">
                      <tr>
                        <th className="px-4 py-3 text-left">名称</th>
                        <th className="px-4 py-3 text-right">涨跌幅</th>
                        <th className="px-4 py-3 text-right">主力净流入</th>
                        <th className="px-4 py-3 text-right">净流入占比</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(toList(data) as any[]).map((item: any, i: number) => (
                        <tr key={i} className="border-t hover:bg-gray-50">
                          <td className="px-4 py-3 font-medium">{item.name}</td>
                          <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                          <td className={`px-4 py-3 text-right font-mono ${changeColor(item.main_net_inflow)}`}>{formatMoneyYuan(item.main_net_inflow)}</td>
                          <td className={`px-4 py-3 text-right font-mono ${changeColor(item.main_net_inflow_percent)}`}>{item.main_net_inflow_percent?.toFixed(2)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* 股票排行 */}
          {tab === "rank" && (
            toList(data).length > 0 ? (
              <table className="w-full">
                <thead className="bg-gray-50 text-sm text-gray-500">
                  <tr>
                    <th className="px-4 py-3 text-left">代码</th>
                    <th className="px-4 py-3 text-left">名称</th>
                    <th className="px-4 py-3 text-right">现价</th>
                    <th className="px-4 py-3 text-right">涨跌幅</th>
                    <th className="px-4 py-3 text-right">成交量</th>
                    <th className="px-4 py-3 text-right">成交额</th>
                    <th className="px-4 py-3 text-right">市盈率</th>
                    <th className="px-4 py-3 text-right">市净率</th>
                  </tr>
                </thead>
                <tbody>
                  {toList(data).map((item: any, i: number) => (
                    <tr key={i} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-500 font-mono text-sm">{item.stock_code}</td>
                      <td className="px-4 py-3 font-medium">{item.stock_name}</td>
                      <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{item.current_price?.toFixed(2) || "-"}</td>
                      <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                      <td className="px-4 py-3 text-right text-gray-500">{formatMoneyYuan(item.volume)}</td>
                      <td className="px-4 py-3 text-right text-gray-500">{formatMoneyYuan(item.amount)}</td>
                      <td className="px-4 py-3 text-right text-gray-500">{item.pe?.toFixed(2) || "-"}</td>
                      <td className="px-4 py-3 text-right text-gray-500">{item.pb?.toFixed(2) || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-8 text-center text-gray-400">暂无数据</div>
            )
          )}

          {/* 持仓分析 */}
          {tab === "portfolio" && data && (
            <div className="p-6">
              {/* 汇总信息 */}
              <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="text-center p-4 bg-gray-50 rounded-xl">
                  <div className="text-2xl font-bold">{data.position_count || 0}</div>
                  <div className="text-gray-500 mt-1">持仓数量</div>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-xl">
                  <div className="text-2xl font-bold">{formatMoneyYuan(data.total_market_value)}</div>
                  <div className="text-gray-500 mt-1">总市值</div>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-xl">
                  <div className={`text-2xl font-bold ${changeColor(data.total_profit)}`}>{formatMoneyYuan(data.total_profit)}</div>
                  <div className="text-gray-500 mt-1">总盈亏</div>
                </div>
                <div className="text-center p-4 bg-gray-50 rounded-xl">
                  <div className={`text-2xl font-bold ${changeColor(data.total_profit_percent)}`}>{formatChange(data.total_profit_percent)}</div>
                  <div className="text-gray-500 mt-1">盈亏比例</div>
                </div>
              </div>

              {/* 持仓列表 */}
              {data.positions?.length > 0 ? (
                <table className="w-full">
                  <thead className="bg-gray-50 text-sm text-gray-500">
                    <tr>
                      <th className="px-4 py-3 text-left">股票</th>
                      <th className="px-4 py-3 text-right">现价</th>
                      <th className="px-4 py-3 text-right">涨跌</th>
                      <th className="px-4 py-3 text-right">市值</th>
                      <th className="px-4 py-3 text-right">盈亏</th>
                      <th className="px-4 py-3 text-right">盈亏比</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.positions.map((item: any, i: number) => (
                      <tr key={i} className="border-t hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="font-medium">{item.stock_name}</div>
                          <div className="text-xs text-gray-400">{item.stock_code}</div>
                        </td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{item.current_price?.toFixed(2) || "-"}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.change_percent)}`}>{formatChange(item.change_percent)}</td>
                        <td className="px-4 py-3 text-right text-gray-500">{formatMoneyYuan(item.market_value)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.profit)}`}>{formatMoneyYuan(item.profit)}</td>
                        <td className={`px-4 py-3 text-right font-mono ${changeColor(item.profit_percent)}`}>{formatChange(item.profit_percent)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-center py-8 text-gray-400">暂无持仓数据，请先添加自选股</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
