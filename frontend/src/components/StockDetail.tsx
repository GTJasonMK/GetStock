"use client";

import { useState, useEffect } from "react";
import api from "@/lib/api";
import StockDecisionTab from "@/components/StockDecisionTab";

interface StockDetailProps {
  code: string;
  onRemove?: () => void;
}

// Tab 类型
type DetailTab = "overview" | "decision" | "fundamental" | "rating" | "shareholders" | "dividend" | "moneyflow";

type StockDetailQuote = {
  stock_name?: string;
  current_price?: number;
  change_percent?: number;
  open_price?: number;
  high_price?: number;
  low_price?: number;
  prev_close?: number;
  volume?: number;
  amount?: number;
};

type StockConcept = {
  concept_name?: string;
  name?: string;
};

type StockFundamental = {
  turnover_rate?: number;
  volume_ratio?: number;
  pe_dynamic?: number;
  pe_ttm?: number;
  pe_static?: number;
  pb?: number;
  roe?: number;
  total_market_cap?: number;
  float_market_cap?: number;
  industry?: string;
  eps?: number;
  bvps?: number;
  profit_yoy?: number;
  revenue_yoy?: number;
};

type FinancialIncomeItem = {
  report_date?: string;
  total_revenue?: number;
  net_profit?: number;
  basic_eps?: number;
};

type StockFinancial = {
  income?: FinancialIncomeItem[];
};

type StockRatingOverview = {
  rating_count?: number;
  consensus_target_price?: number;
  max_target_price?: number;
  min_target_price?: number;
};

type StockDetailData = {
  quote?: StockDetailQuote;
  basic?: { name?: string };
  concepts?: StockConcept[];
  rating?: StockRatingOverview;
  fundamental?: StockFundamental;
  financial?: StockFinancial;
};

type RatingReport = {
  title?: string;
  org_name?: string;
  author?: string;
  publish_date?: string;
  rating?: string;
  target_price?: number;
};

type StockRating = {
  ratings?: Record<string, number>;
  consensus_target_price?: number;
  max_target_price?: number;
  min_target_price?: number;
  reports?: RatingReport[];
};

type ShareholderItem = {
  end_date?: string;
  holder_num?: number;
  holder_num_change_pct?: number;
  avg_hold_amount?: number;
};

type TopHolderItem = {
  holder_name?: string;
  hold_num?: number;
  hold_ratio?: number;
  change?: number;
};

type DividendItem = {
  report_date?: string;
  plan?: string;
  ex_dividend_date?: string;
  progress?: string;
};

type MoneyFlowItem = {
  date?: string;
  main_net_inflow?: number;
  main_net_inflow_pct?: number;
  super_large_net_inflow?: number;
  large_net_inflow?: number;
  close?: number;
  change_percent?: number;
};

export default function StockDetail({ code, onRemove }: StockDetailProps) {
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<StockDetailData | null>(null);
  const [rating, setRating] = useState<StockRating | null>(null);
  const [shareholders, setShareholders] = useState<ShareholderItem[]>([]);
  const [topHolders, setTopHolders] = useState<TopHolderItem[]>([]);
  const [dividend, setDividend] = useState<DividendItem[]>([]);
  const [moneyFlow, setMoneyFlow] = useState<MoneyFlowItem[]>([]);

  type TabMeta = {
    loaded: boolean;
    loading: boolean;
    error: string | null;
  };

  const [tabMeta, setTabMeta] = useState<Record<DetailTab, TabMeta>>({
    overview: { loaded: true, loading: false, error: null },
    decision: { loaded: true, loading: false, error: null },
    fundamental: { loaded: true, loading: false, error: null },
    rating: { loaded: false, loading: false, error: null },
    shareholders: { loaded: false, loading: false, error: null },
    dividend: { loaded: false, loading: false, error: null },
    moneyflow: { loaded: false, loading: false, error: null },
  });

  const resetAsyncTabs = () => {
    setTabMeta((prev) => ({
      ...prev,
      rating: { loaded: false, loading: false, error: null },
      shareholders: { loaded: false, loading: false, error: null },
      dividend: { loaded: false, loading: false, error: null },
      moneyflow: { loaded: false, loading: false, error: null },
    }));
  };

  const retryTab = (tab: DetailTab) => {
    if (!["rating", "shareholders", "dividend", "moneyflow"].includes(tab)) return;
    setTabMeta((prev) => ({ ...prev, [tab]: { loaded: false, loading: false, error: null } }));
  };

  // 获取股票详情
  useEffect(() => {
    setLoading(true);
    resetAsyncTabs();
    setRating(null);
    setShareholders([]);
    setTopHolders([]);
    setDividend([]);
    setMoneyFlow([]);

    api.getStockDetail(code)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [code]);

  // 切换 tab 时按需加载数据（同时记录加载状态/错误，避免“静默空白/永远加载中”）
  useEffect(() => {
    const meta = tabMeta[activeTab];
    const isAsyncTab = ["rating", "shareholders", "dividend", "moneyflow"].includes(activeTab);
    if (!isAsyncTab) return;
    if (meta.loaded || meta.loading) return;

    const start = () => setTabMeta((prev) => ({ ...prev, [activeTab]: { loaded: false, loading: true, error: null } }));
    const doneOk = () => setTabMeta((prev) => ({ ...prev, [activeTab]: { loaded: true, loading: false, error: null } }));
    const doneErr = (msg: string) => setTabMeta((prev) => ({ ...prev, [activeTab]: { loaded: true, loading: false, error: msg } }));

    if (activeTab === "rating") {
      start();
      api
        .getStockRating(code)
        .then((v) => setRating(v as StockRating))
        .then(() => doneOk())
        .catch((e: unknown) => {
          setRating(null);
          doneErr(e instanceof Error ? e.message : String(e || "获取机构评级失败"));
        });
      return;
    }

    if (activeTab === "shareholders") {
      start();
      Promise.all([api.getStockShareholders(code), api.getStockTopHolders(code, "float")])
        .then(([sh, holders]) => {
          setShareholders(Array.isArray(sh) ? (sh as ShareholderItem[]) : []);
          setTopHolders(Array.isArray(holders) ? (holders as TopHolderItem[]) : []);
        })
        .then(() => doneOk())
        .catch((e: unknown) => {
          setShareholders([]);
          setTopHolders([]);
          doneErr(e instanceof Error ? e.message : String(e || "获取股东信息失败"));
        });
      return;
    }

    if (activeTab === "dividend") {
      start();
      api
        .getStockDividend(code)
        .then((v) => setDividend(Array.isArray(v) ? (v as DividendItem[]) : []))
        .then(() => doneOk())
        .catch((e: unknown) => {
          setDividend([]);
          doneErr(e instanceof Error ? e.message : String(e || "获取分红送转失败"));
        });
      return;
    }

    if (activeTab === "moneyflow") {
      start();
      api
        .getStockMoneyFlowHistory(code, 30)
        .then((v) => setMoneyFlow(Array.isArray(v) ? (v as MoneyFlowItem[]) : []))
        .then(() => doneOk())
        .catch((e: unknown) => {
          setMoneyFlow([]);
          doneErr(e instanceof Error ? e.message : String(e || "获取资金流向失败"));
        });
    }
  }, [activeTab, code, tabMeta]);

  const toNumber = (v: unknown): number | null => {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") return Number.isFinite(v) ? v : null;
    if (typeof v === "string") {
      const s = v.trim();
      if (!s) return null;
      const n = Number(s);
      return Number.isFinite(n) ? n : null;
    }
    return null;
  };

  const formatFixed = (v: unknown, digits: number = 2) => {
    const n = toNumber(v);
    if (n === null) return "-";
    return n.toFixed(digits);
  };

  const formatMoney = (v: unknown) => {
    const n = toNumber(v);
    if (n === null) return "-";
    if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + "亿";
    if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + "万";
    return n.toFixed(2);
  };

  const formatPercent = (v: unknown) => {
    const n = toNumber(v);
    if (n === null) return "-";
    return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
  };

  const formatPercentPlain = (v: unknown, digits: number = 2) => {
    const n = toNumber(v);
    if (n === null) return "-";
    return `${n.toFixed(digits)}%`;
  };

  const changeColor = (v: unknown) => {
    const n = toNumber(v);
    if (n === null) return "";
    return n > 0 ? "text-red-600" : n < 0 ? "text-green-600" : "";
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400">加载中...</div>;
  }

  if (!detail) {
    return <div className="flex items-center justify-center h-64 text-gray-400">暂无数据</div>;
  }

  const quote = detail.quote;
  const fundamental = detail.fundamental;
  const financial = detail.financial;
  const concepts = detail.concepts ?? [];
  const detailRating = detail.rating;
  const incomeList = financial?.income ?? [];
  const ratingReports = rating?.reports ?? [];

  return (
    <div className="h-full flex flex-col">
      {/* 头部信息 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold">{quote?.stock_name || detail.basic?.name || code}</h2>
          <p className="text-gray-500">{code}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className={`text-3xl font-bold ${changeColor(quote?.change_percent)}`}>
              {quote?.current_price?.toFixed(2) || "-"}
            </div>
            <div className={`text-sm ${changeColor(quote?.change_percent)}`}>
              {formatPercent(quote?.change_percent)}
            </div>
          </div>
          {onRemove && (
            <button type="button" onClick={onRemove} className="px-4 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg">
              移除自选
            </button>
          )}
        </div>
      </div>

      {/* Tab 导航 */}
      <div className="flex gap-1 mb-4 bg-gray-100 rounded-lg p-1 w-fit">
        {[
          { key: "overview", label: "概览" },
          { key: "decision", label: "决策仪表盘" },
          { key: "fundamental", label: "估值指标" },
          { key: "rating", label: "机构评级" },
          { key: "shareholders", label: "股东信息" },
          { key: "dividend", label: "分红送转" },
          { key: "moneyflow", label: "资金流向" },
        ].map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setActiveTab(t.key as DetailTab)}
            className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
              activeTab === t.key ? "bg-white shadow text-blue-600" : "text-gray-600 hover:text-gray-900"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto">
        {/* 概览 */}
        {activeTab === "overview" && (
          <div className="space-y-4">
            {/* 行情卡片 */}
            <div className="grid grid-cols-4 gap-4">
              <InfoCard label="今开" value={quote?.open_price?.toFixed(2)} />
              <InfoCard label="最高" value={quote?.high_price?.toFixed(2)} color="text-red-600" />
              <InfoCard label="最低" value={quote?.low_price?.toFixed(2)} color="text-green-600" />
              <InfoCard label="昨收" value={quote?.prev_close?.toFixed(2)} />
              <InfoCard label="成交量" value={formatMoney(quote?.volume)} />
              <InfoCard label="成交额" value={formatMoney(quote?.amount)} />
              <InfoCard label="换手率" value={formatPercent(fundamental?.turnover_rate)} />
              <InfoCard label="量比" value={formatFixed(fundamental?.volume_ratio)} />
            </div>

            {/* 概念板块 */}
            {concepts.length > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">所属概念</h3>
                <div className="flex flex-wrap gap-2">
                  {concepts.slice(0, 10).map((c: StockConcept, i: number) => (
                    <span key={i} className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm">
                      {c.concept_name || c.name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 评级摘要 */}
            {(detailRating?.rating_count ?? 0) > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">机构评级概览</h3>
                <div className="grid grid-cols-4 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-blue-600">{detailRating?.rating_count ?? 0}</div>
                    <div className="text-xs text-gray-500">评级数量</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-red-600">
                      {formatFixed(detailRating?.consensus_target_price)}
                    </div>
                    <div className="text-xs text-gray-500">一致目标价</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-medium">{formatFixed(detailRating?.max_target_price)}</div>
                    <div className="text-xs text-gray-500">最高目标价</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-medium">{formatFixed(detailRating?.min_target_price)}</div>
                    <div className="text-xs text-gray-500">最低目标价</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 决策仪表盘 */}
        {activeTab === "decision" && (
          <StockDecisionTab
            code={code}
            stockName={quote?.stock_name || detail.basic?.name || code}
          />
        )}

        {/* 估值指标 */}
        {activeTab === "fundamental" && fundamental && (
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-4">
              <InfoCard label="PE(动态)" value={formatFixed(fundamental.pe_dynamic)} />
              <InfoCard label="PE(TTM)" value={formatFixed(fundamental.pe_ttm)} />
              <InfoCard label="PE(静态)" value={formatFixed(fundamental.pe_static)} />
              <InfoCard label="PB" value={formatFixed(fundamental.pb)} />
              <InfoCard label="ROE" value={formatPercent(fundamental.roe)} />
              <InfoCard label="总市值" value={formatMoney(fundamental.total_market_cap)} />
              <InfoCard label="流通市值" value={formatMoney(fundamental.float_market_cap)} />
              <InfoCard label="所属行业" value={fundamental.industry} />
            </div>

            {/* 每股指标 */}
            <div className="bg-white rounded-xl p-4 shadow-sm">
              <h3 className="font-medium mb-3">每股指标</h3>
              <div className="grid grid-cols-4 gap-4 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">每股收益</span>
                  <span>{formatFixed(fundamental.eps, 3)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">每股净资产</span>
                  <span>{formatFixed(fundamental.bvps, 2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">净利润同比</span>
                  <span className={changeColor(fundamental.profit_yoy)}>
                    {formatPercent(fundamental.profit_yoy)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">营收同比</span>
                  <span className={changeColor(fundamental.revenue_yoy)}>
                    {formatPercent(fundamental.revenue_yoy)}
                  </span>
                </div>
              </div>
            </div>

            {/* 财务报表 */}
            {incomeList.length > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">财务摘要</h3>
                <table className="w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">报告期</th>
                      <th className="text-right py-2">营业收入</th>
                      <th className="text-right py-2">净利润</th>
                      <th className="text-right py-2">每股收益</th>
                    </tr>
                  </thead>
                  <tbody>
                    {incomeList.slice(0, 4).map((item: FinancialIncomeItem, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="py-2">{item.report_date}</td>
                        <td className="text-right">{formatMoney(item.total_revenue)}</td>
                        <td className="text-right">{formatMoney(item.net_profit)}</td>
                        <td className="text-right">{formatFixed(item.basic_eps, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* 机构评级 */}
        {activeTab === "rating" && (
          <div className="space-y-4">
            {rating ? (
              <>
                {/* 评级分布 */}
                <div className="bg-white rounded-xl p-4 shadow-sm">
                  <h3 className="font-medium mb-3">评级分布</h3>
                  <div className="flex gap-4">
                    {Object.entries(rating.ratings || {}).map(([k, v]) => (
                      <div key={k} className="text-center px-4 py-2 bg-gray-50 rounded-lg">
                        <div className="text-xl font-bold">{v as number}</div>
                        <div className="text-xs text-gray-500">{k}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 目标价 */}
                <div className="grid grid-cols-3 gap-4">
                  <InfoCard label="一致目标价" value={formatFixed(rating.consensus_target_price)} color="text-red-600" />
                  <InfoCard label="最高目标价" value={formatFixed(rating.max_target_price)} />
                  <InfoCard label="最低目标价" value={formatFixed(rating.min_target_price)} />
                </div>

                {/* 研报列表 */}
                {ratingReports.length > 0 && (
                  <div className="bg-white rounded-xl p-4 shadow-sm">
                    <h3 className="font-medium mb-3">最新研报</h3>
                    <div className="space-y-3">
                      {ratingReports.slice(0, 10).map((r: RatingReport, i: number) => (
                        <div key={i} className="flex items-start justify-between py-2 border-b last:border-0">
                          <div className="flex-1">
                            <div className="text-sm font-medium line-clamp-1">{r.title}</div>
                            <div className="text-xs text-gray-500 mt-1">
                              {r.org_name} | {r.author} | {r.publish_date}
                            </div>
                          </div>
                          <div className="text-right ml-4">
                            {r.rating && <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs">{r.rating}</span>}
                            {r.target_price && (
                              <div className="text-sm text-red-600 mt-1">目标价: {r.target_price}</div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              tabMeta.rating.loading ? (
                <div className="text-center py-12 text-gray-400">加载评级数据中...</div>
              ) : tabMeta.rating.error ? (
                <div role="alert" className="p-4 bg-red-50 text-red-700 rounded-xl border border-red-100">
                  <div className="font-medium">获取机构评级失败</div>
                  <div className="text-sm mt-1 break-words">{tabMeta.rating.error}</div>
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("rating")} className="px-3 py-1.5 text-sm rounded-md bg-red-600 text-white hover:opacity-90">
                      重试
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  暂无评级数据
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("rating")} className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90">
                      刷新
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        )}

        {/* 股东信息 */}
        {activeTab === "shareholders" && (
          <div className="space-y-4">
            {/* 股东人数变化 */}
            {shareholders.length > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">股东人数变化</h3>
                <table className="w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">日期</th>
                      <th className="text-right py-2">股东人数</th>
                      <th className="text-right py-2">变动比例</th>
                      <th className="text-right py-2">人均持股</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shareholders.map((item: ShareholderItem, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="py-2">{item.end_date}</td>
                        <td className="text-right">{item.holder_num?.toLocaleString() || "-"}</td>
                        <td className={`text-right ${changeColor(item.holder_num_change_pct)}`}>
                          {formatPercent(item.holder_num_change_pct)}
                        </td>
                        <td className="text-right">{item.avg_hold_amount?.toLocaleString() || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* 十大流通股东 */}
            {topHolders.length > 0 && (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">十大流通股东</h3>
                <table className="w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">股东名称</th>
                      <th className="text-right py-2">持股数量</th>
                      <th className="text-right py-2">持股比例</th>
                      <th className="text-right py-2">变动</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topHolders.map((item: TopHolderItem, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="py-2">{item.holder_name}</td>
                        <td className="text-right">{formatMoney(item.hold_num)}</td>
                        <td className="text-right">{formatPercentPlain(item.hold_ratio)}</td>
                        <td className={`text-right ${changeColor(item.change)}`}>
                          {item.change ? formatMoney(item.change) : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {shareholders.length === 0 && topHolders.length === 0 && (
              tabMeta.shareholders.loading ? (
                <div className="text-center py-12 text-gray-400">加载股东数据中...</div>
              ) : tabMeta.shareholders.error ? (
                <div role="alert" className="p-4 bg-red-50 text-red-700 rounded-xl border border-red-100">
                  <div className="font-medium">获取股东数据失败</div>
                  <div className="text-sm mt-1 break-words">{tabMeta.shareholders.error}</div>
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("shareholders")} className="px-3 py-1.5 text-sm rounded-md bg-red-600 text-white hover:opacity-90">
                      重试
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  暂无股东数据
                  <div className="text-xs text-gray-400 mt-2">可能原因：非A股/停牌/数据源限制。</div>
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("shareholders")} className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90">
                      刷新
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        )}

        {/* 分红送转 */}
        {activeTab === "dividend" && (
          <div className="space-y-4">
            {dividend.length > 0 ? (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">分红送转历史</h3>
                <table className="w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">报告期</th>
                      <th className="text-left py-2">分配方案</th>
                      <th className="text-right py-2">除权除息日</th>
                      <th className="text-right py-2">进度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dividend.map((item: DividendItem, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="py-2">{item.report_date}</td>
                        <td className="py-2 max-w-xs truncate">{item.plan || "-"}</td>
                        <td className="text-right">{item.ex_dividend_date || "-"}</td>
                        <td className="text-right">
                          <span className={`px-2 py-0.5 rounded text-xs ${
                            item.progress?.includes("实施") ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                          }`}>
                            {item.progress || "-"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              tabMeta.dividend.loading ? (
                <div className="text-center py-12 text-gray-400">加载分红数据中...</div>
              ) : tabMeta.dividend.error ? (
                <div role="alert" className="p-4 bg-red-50 text-red-700 rounded-xl border border-red-100">
                  <div className="font-medium">获取分红送转失败</div>
                  <div className="text-sm mt-1 break-words">{tabMeta.dividend.error}</div>
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("dividend")} className="px-3 py-1.5 text-sm rounded-md bg-red-600 text-white hover:opacity-90">
                      重试
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  暂无分红数据
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("dividend")} className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90">
                      刷新
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        )}

        {/* 资金流向 */}
        {activeTab === "moneyflow" && (
          <div className="space-y-4">
            {moneyFlow.length > 0 ? (
              <div className="bg-white rounded-xl p-4 shadow-sm">
                <h3 className="font-medium mb-3">近30日资金流向</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-gray-500">
                      <tr>
                        <th className="text-left py-2">日期</th>
                        <th className="text-right py-2">主力净流入</th>
                        <th className="text-right py-2">主力净占比</th>
                        <th className="text-right py-2">超大单</th>
                        <th className="text-right py-2">大单</th>
                        <th className="text-right py-2">收盘价</th>
                        <th className="text-right py-2">涨跌幅</th>
                      </tr>
                    </thead>
                    <tbody>
                      {moneyFlow.slice(0, 20).map((item: MoneyFlowItem, i: number) => (
                        <tr key={i} className="border-t">
                          <td className="py-2">{item.date}</td>
                          <td className={`text-right ${changeColor(item.main_net_inflow)}`}>
                            {formatMoney(item.main_net_inflow)}
                          </td>
                          <td className={`text-right ${changeColor(item.main_net_inflow_pct)}`}>
                            {formatPercent(item.main_net_inflow_pct)}
                          </td>
                          <td className={`text-right ${changeColor(item.super_large_net_inflow)}`}>
                            {formatMoney(item.super_large_net_inflow)}
                          </td>
                          <td className={`text-right ${changeColor(item.large_net_inflow)}`}>
                            {formatMoney(item.large_net_inflow)}
                          </td>
                          <td className="text-right">{formatFixed(item.close)}</td>
                          <td className={`text-right ${changeColor(item.change_percent)}`}>
                            {formatPercent(item.change_percent)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              tabMeta.moneyflow.loading ? (
                <div className="text-center py-12 text-gray-400">加载资金流向数据中...</div>
              ) : tabMeta.moneyflow.error ? (
                <div role="alert" className="p-4 bg-red-50 text-red-700 rounded-xl border border-red-100">
                  <div className="font-medium">获取资金流向失败</div>
                  <div className="text-sm mt-1 break-words">{tabMeta.moneyflow.error}</div>
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("moneyflow")} className="px-3 py-1.5 text-sm rounded-md bg-red-600 text-white hover:opacity-90">
                      重试
                    </button>
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  暂无资金流向数据
                  <div className="mt-3">
                    <button type="button" onClick={() => retryTab("moneyflow")} className="px-3 py-1.5 text-sm rounded-md bg-[var(--accent)] text-white hover:opacity-90">
                      刷新
                    </button>
                  </div>
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// 信息卡片组件
function InfoCard({ label, value, color = "" }: { label: string; value?: string | number | null; color?: string }) {
  return (
    <div className="bg-white rounded-xl p-4 shadow-sm">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-medium ${color}`}>{value ?? "-"}</div>
    </div>
  );
}
