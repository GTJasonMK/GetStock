"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { useToast } from "@/components/ui/ToastProvider";

type Props = {
  code: string;
  stockName?: string;
};

type SectionKey = "news" | "sentiment" | "notices" | "reports";

type ChecklistStatus = "pass" | "warn" | "fail";

type BuySignal =
  | "strong_buy"
  | "buy"
  | "weak_buy"
  | "hold"
  | "weak_sell"
  | "sell"
  | "strong_sell";

type DecisionChecklistItem = {
  key: string;
  label: string;
  status: ChecklistStatus;
  message: string;
};

type DecisionPoints = {
  ideal_buy?: number | null;
  sniper_buy?: number | null;
  stop_loss?: number | null;
  target_1?: number | null;
  target_2?: number | null;
};

type DecisionDashboard = {
  stock_code: string;
  stock_name: string;
  buy_signal: BuySignal;
  score: number;
  summary: string;
  points: DecisionPoints;
  checklist: DecisionChecklistItem[];
  risks: string[];
  generated_at: string;
  data_sources: string[];
  technical?: { current_price?: number } | null;
};

type NewsSearchItem = {
  news_id: string;
  title: string;
  content: string;
  source: string;
  publish_time?: string | null;
  url: string;
  image_url?: string | null;
};

type StockNoticeItem = {
  title: string;
  notice_date: string;
  notice_type?: string;
  url?: string;
};

type StockResearchReportItem = {
  title: string;
  publish_date: string;
  org_name?: string;
  author?: string;
  rating?: string;
  target_price?: number | null;
  url?: string;
};

type NewsSentiment = {
  overall_sentiment: string;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  news_count: number;
};

const toFiniteNumber = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

const formatPrice = (v?: number | null) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(2) : "-");

const formatDateTime = (v?: string | null) => {
  if (!v) return "-";
  return String(v).replace("T", " ").slice(0, 16);
};

const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* ignore */ }

  try {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "true");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
};

const statusMeta: Record<ChecklistStatus, { icon: string; cls: string }> = {
  pass: { icon: "✅", cls: "text-emerald-700" },
  warn: { icon: "⚠️", cls: "text-amber-700" },
  fail: { icon: "❌", cls: "text-red-700" },
};

const signalMeta: Record<BuySignal, { label: string; cls: string }> = {
  strong_buy: { label: "强买入", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" },
  buy: { label: "买入", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" },
  weak_buy: { label: "轻仓/关注", cls: "bg-blue-50 text-blue-700 border-blue-100" },
  hold: { label: "观望", cls: "bg-gray-50 text-gray-700 border-gray-200" },
  weak_sell: { label: "减仓", cls: "bg-amber-50 text-amber-800 border-amber-100" },
  sell: { label: "卖出", cls: "bg-red-50 text-red-700 border-red-100" },
  strong_sell: { label: "强卖出", cls: "bg-red-50 text-red-700 border-red-100" },
};

export default function StockDecisionTab({ code, stockName }: Props) {
  const toast = useToast();
  const [dashboard, setDashboard] = useState<DecisionDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const [openSections, setOpenSections] = useState<Record<SectionKey, boolean>>({
    news: false,
    sentiment: false,
    notices: false,
    reports: false,
  });

  const [newsKeyword, setNewsKeyword] = useState("");
  const [newsEngine, setNewsEngine] = useState<string | null>(null);
  const [newsItems, setNewsItems] = useState<NewsSearchItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string>("");

  const [sentiment, setSentiment] = useState<NewsSentiment | null>(null);
  const [sentimentLoading, setSentimentLoading] = useState(false);
  const [sentimentError, setSentimentError] = useState<string>("");

  const [notices, setNotices] = useState<StockNoticeItem[]>([]);
  const [noticesLoading, setNoticesLoading] = useState(false);
  const [noticesError, setNoticesError] = useState<string>("");

  const [reports, setReports] = useState<StockResearchReportItem[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportsError, setReportsError] = useState<string>("");

  useEffect(() => {
    setLoading(true);
    setError(null);
    setDashboard(null);
    api
      .getDecisionDashboard(code, 120, true)
      .then(setDashboard)
      .catch((e) => setError(e instanceof Error ? e.message : "获取决策仪表盘失败"))
      .finally(() => setLoading(false));
  }, [code, reloadToken]);

  useEffect(() => {
    const kw = (stockName || code || "").trim();
    setNewsKeyword(kw);
  }, [code, stockName]);

  // 切换股票时清理“可选信息源”的旧数据，避免残留误导
  useEffect(() => {
    setNewsItems([]);
    setNewsError("");
    setNewsEngine(null);
    setSentiment(null);
    setSentimentError("");
    setNotices([]);
    setNoticesError("");
    setReports([]);
    setReportsError("");
  }, [code]);

  const toggleSection = (key: SectionKey) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const points = dashboard?.points;
  const meta = dashboard ? signalMeta[dashboard.buy_signal] : null;
  const currentPrice = dashboard ? toFiniteNumber(dashboard.technical?.current_price) : null;
  const stopLoss = toFiniteNumber(points?.stop_loss);
  const target1 = toFiniteNumber(points?.target_1);
  const rrInfo =
    currentPrice !== null &&
    stopLoss !== null &&
    target1 !== null &&
    currentPrice > stopLoss &&
    target1 > currentPrice
      ? {
          risk: currentPrice - stopLoss,
          reward: target1 - currentPrice,
          riskPct: ((currentPrice - stopLoss) / currentPrice) * 100,
          rewardPct: ((target1 - currentPrice) / currentPrice) * 100,
          rr: (target1 - currentPrice) / (currentPrice - stopLoss),
        }
      : null;

  const handleCopyPlan = async () => {
    if (!dashboard) return;
    const lines: string[] = [
      `交易计划 - ${dashboard.stock_name}（${dashboard.stock_code}）`,
      `信号：${meta ? meta.label : dashboard.buy_signal} / 评分：${dashboard.score}`,
      `生成时间：${formatDateTime(dashboard.generated_at)}`,
      `当前价：${formatPrice(currentPrice)}`,
      `点位：理想买入 ${formatPrice(points?.ideal_buy)}，狙击买入 ${formatPrice(points?.sniper_buy)}，止损 ${formatPrice(points?.stop_loss)}，目标1 ${formatPrice(points?.target_1)}，目标2 ${formatPrice(points?.target_2)}`,
    ];
    if (rrInfo) {
      lines.push(`风险：${rrInfo.risk.toFixed(2)}（${rrInfo.riskPct.toFixed(1)}%），收益：${rrInfo.reward.toFixed(2)}（${rrInfo.rewardPct.toFixed(1)}%），盈亏比：${rrInfo.rr.toFixed(2)}`);
    }
    lines.push("");
    lines.push("检查清单：");
    for (const item of checklist) {
      lines.push(`- [${item.status}] ${item.label}：${item.message}`);
    }
    lines.push("");
    lines.push("风险点：");
    for (const r of risks) {
      lines.push(`- ${r}`);
    }
    if (dashboard.data_sources?.length) {
      lines.push("");
      lines.push(`数据源：${dashboard.data_sources.join(", ")}`);
    }

    const ok = await copyToClipboard(lines.join("\n"));
    if (ok) {
      toast.push({ variant: "success", title: "已复制", message: "交易计划已复制到剪贴板" });
    } else {
      toast.push({ variant: "error", title: "复制失败", message: "浏览器不支持剪贴板，请手动复制" });
    }
  };

  const fetchNotices = useCallback(async (force: boolean = false) => {
    setNoticesLoading(true);
    setNoticesError("");
    try {
      if (force) api.invalidatePrefix(`/stock/${encodeURIComponent(code)}/notices`);
      const data = await api.getStockNotices(code, 20);
      setNotices(Array.isArray(data) ? data : []);
    } catch (e) {
      setNotices([]);
      setNoticesError(e instanceof Error ? e.message : "获取公告失败");
    } finally {
      setNoticesLoading(false);
    }
  }, [code]);

  const fetchReports = useCallback(async (force: boolean = false) => {
    setReportsLoading(true);
    setReportsError("");
    try {
      if (force) api.invalidatePrefix(`/stock/${encodeURIComponent(code)}/research-reports`);
      const data = await api.getStockResearchReports(code, 10);
      setReports(Array.isArray(data) ? data : []);
    } catch (e) {
      setReports([]);
      setReportsError(e instanceof Error ? e.message : "获取研报失败");
    } finally {
      setReportsLoading(false);
    }
  }, [code]);

  const fetchNews = useCallback(async () => {
    const kw = newsKeyword.trim();
    if (!kw) return;
    setNewsLoading(true);
    setNewsError("");
    setNewsEngine(null);
    try {
      const data = await api.searchNews(kw, undefined, 10);
      setNewsItems(data?.items || []);
      setNewsEngine(data?.engine ?? null);
    } catch (e) {
      setNewsItems([]);
      setNewsError(e instanceof Error ? e.message : "检索舆情失败");
    } finally {
      setNewsLoading(false);
    }
  }, [newsKeyword]);

  // 舆情情绪（会消耗搜索额度 + AI 调用，默认不自动触发）
  const fetchSentiment = useCallback(async (force: boolean = false) => {
    setSentimentLoading(true);
    setSentimentError("");
    try {
      if (force) api.invalidatePrefix(`/ai/sentiment/news/${encodeURIComponent(code)}`);
      const data = await api.getNewsSentiment(code);
      setSentiment(data);
    } catch (e) {
      setSentiment(null);
      setSentimentError(e instanceof Error ? e.message : "分析舆情情绪失败");
    } finally {
      setSentimentLoading(false);
    }
  }, [code]);

  const sentimentLabel = (v?: string) => {
    if (v === "positive") return { label: "偏积极", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" };
    if (v === "negative") return { label: "偏消极", cls: "bg-red-50 text-red-700 border-red-100" };
    return { label: "中性", cls: "bg-gray-50 text-gray-700 border-gray-200" };
  };

  // 打开 section 时按需加载（不做自动舆情搜索，避免消耗搜索额度）
  useEffect(() => {
    if (!openSections.notices) return;
    if (noticesLoading) return;
    if (notices.length > 0) return;
    if (noticesError) return;
    fetchNotices();
  }, [openSections.notices, noticesLoading, notices.length, noticesError, fetchNotices]);

  useEffect(() => {
    if (!openSections.reports) return;
    if (reportsLoading) return;
    if (reports.length > 0) return;
    if (reportsError) return;
    fetchReports();
  }, [openSections.reports, reportsLoading, reports.length, reportsError, fetchReports]);

  const checklist = useMemo(() => dashboard?.checklist || [], [dashboard?.checklist]);
  const risks = useMemo(() => dashboard?.risks || [], [dashboard?.risks]);

  if (loading) return <div className="text-center py-12 text-gray-400">加载决策仪表盘中...</div>;
  if (error || !dashboard) {
    return (
      <div role="alert" className="p-4 bg-red-50 text-red-700 rounded-xl border border-red-100">
        <div className="font-medium">获取决策仪表盘失败</div>
        <div className="text-sm mt-1 break-words">{error || "暂无数据"}</div>
        <div className="mt-3">
          <button type="button" onClick={() => setReloadToken((x) => x + 1)} className="px-3 py-1.5 text-sm rounded-md bg-red-600 text-white hover:opacity-90">
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 核心结论 */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-[color:var(--border-color)]">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex items-center gap-2">
                {meta && (
                  <span className={`px-2 py-0.5 text-xs rounded-md border ${meta.cls}`}>
                    {meta.label}
                  </span>
                )}
                <span className="text-sm text-gray-500">评分</span>
                <span className="font-mono text-sm font-semibold">{dashboard.score}</span>
                <span className="text-xs text-gray-400 truncate">
                  {dashboard.generated_at ? `生成于：${formatDateTime(dashboard.generated_at)}` : ""}
                  {dashboard.data_sources?.length ? ` · 数据源：${dashboard.data_sources.join(", ")}` : ""}
                </span>
              </div>
              <button type="button" onClick={handleCopyPlan} className="text-xs text-gray-500 hover:text-gray-800 shrink-0">
                复制计划
              </button>
            </div>
            <div className="mt-2 text-gray-900 leading-6">{dashboard.summary || "—"}</div>
          </div>

          {/* 点位 */}
          <div className="shrink-0 w-full md:w-[360px]">
            <div className="grid grid-cols-2 gap-2">
              <Point label="理想买入(MA5)" value={formatPrice(points?.ideal_buy)} />
              <Point label="狙击买入(支撑)" value={formatPrice(points?.sniper_buy)} />
              <Point label="止损位" value={formatPrice(points?.stop_loss)} cls="text-red-700" />
              <Point label="目标位1" value={formatPrice(points?.target_1)} cls="text-emerald-700" />
              <Point label="目标位2" value={formatPrice(points?.target_2)} cls="text-emerald-700" />
              <div className="bg-[var(--bg-surface-muted)] rounded-lg p-3 flex items-center justify-between">
                <div className="text-xs text-gray-500">当前</div>
                <div className="font-mono font-semibold">{formatPrice(currentPrice)}</div>
              </div>
            </div>
            {rrInfo && (
              <div className="mt-2 text-xs text-gray-500 font-mono">
                风险 {rrInfo.risk.toFixed(2)}（{rrInfo.riskPct.toFixed(1)}%） / 收益 {rrInfo.reward.toFixed(2)}（{rrInfo.rewardPct.toFixed(1)}%） / 盈亏比 {rrInfo.rr.toFixed(2)}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 检查清单 */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-[color:var(--border-color)]">
        <div className="flex items-center justify-between">
          <h3 className="font-medium">检查清单</h3>
          <button type="button" onClick={() => setReloadToken((x) => x + 1)} className="text-xs text-gray-500 hover:text-gray-800">
            刷新
          </button>
        </div>
        <div className="mt-3 space-y-2">
          {checklist.length > 0 ? (
            checklist.map((item) => {
              const sm = statusMeta[item.status];
              return (
                <div key={item.key} className="flex items-start gap-2 text-sm">
                  <span className={sm.cls}>{sm.icon}</span>
                  <div className="min-w-0">
                    <div className="text-gray-900">
                      <span className="font-medium">{item.label}：</span>
                      <span className="text-gray-700">{item.message}</span>
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            <div className="text-sm text-gray-500">暂无检查项</div>
          )}
        </div>
      </div>

      {/* 风险点 */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-[color:var(--border-color)]">
        <h3 className="font-medium">风险点</h3>
        <div className="mt-3">
          {risks.length > 0 ? (
            <ul className="list-disc pl-5 space-y-1 text-sm text-gray-700">
              {risks.map((r, i) => (
                <li key={i} className="break-words">{r}</li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-gray-500">暂无明显风险提示（仅基于技术面规则）。</div>
          )}
        </div>
      </div>

      {/* 可选信息源 */}
      <div className="bg-white rounded-xl p-4 shadow-sm border border-[color:var(--border-color)]">
        <h3 className="font-medium">可选信息源</h3>
        <div className="mt-3 space-y-2">
          <Section
            title="舆情/新闻（可选检索）"
            open={openSections.news}
            onToggle={() => toggleSection("news")}
          >
            <div className="flex flex-col md:flex-row gap-2">
              <input
                value={newsKeyword}
                onChange={(e) => setNewsKeyword(e.target.value)}
                placeholder="输入关键词（默认股票名称/代码）"
                className="input flex-1"
              />
                <button
                  type="button"
                  onClick={fetchNews}
                  disabled={!newsKeyword.trim() || newsLoading}
                  className="btn btn-primary"
                >
                {newsLoading ? "检索中..." : "检索"}
              </button>
            </div>
            {!!newsEngine && (
              <div className="mt-2 text-xs text-gray-500">引擎：{newsEngine}</div>
            )}
            {!!newsError && (
              <div role="alert" className="mt-3 p-3 rounded-lg bg-amber-50 text-amber-800 text-sm border border-amber-100">
                {newsError}
              </div>
            )}
            <div className="mt-3 space-y-2">
              {newsItems.length > 0 ? (
                newsItems.map((n) => (
                  <a
                    key={n.news_id}
                    href={n.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block p-3 rounded-lg border hover:bg-[var(--bg-surface-muted)] transition-colors"
                  >
                    <div className="text-sm font-medium text-gray-900">{n.title}</div>
                    <div className="mt-1 text-xs text-gray-500 flex items-center gap-2">
                      <span>{n.source}</span>
                      {n.publish_time ? <span>{String(n.publish_time).slice(0, 16).replace("T", " ")}</span> : null}
                    </div>
                    {n.content ? <div className="mt-2 text-sm text-gray-700 line-clamp-2">{n.content}</div> : null}
                  </a>
                ))
              ) : (
                <div className="text-sm text-gray-500">未检索或暂无结果。</div>
              )}
            </div>
          </Section>

          <Section title="舆情情绪（AI，可选）" open={openSections.sentiment} onToggle={() => toggleSection("sentiment")}>
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
              <div className="text-xs text-gray-500">
                说明：将基于“股票名称/代码”检索相关新闻并逐条做情绪分析，会消耗搜索额度与 AI 调用次数。
              </div>
              <div className="flex items-center gap-2 justify-end">
                <button type="button" onClick={() => fetchSentiment(true)} disabled={sentimentLoading} className="btn btn-secondary">
                  重新分析
                </button>
                <button type="button" onClick={() => fetchSentiment(false)} disabled={sentimentLoading} className="btn btn-primary">
                  {sentimentLoading ? "分析中..." : "开始分析"}
                </button>
              </div>
            </div>

            {!!sentimentError && (
              <div role="alert" className="mt-3 p-3 rounded-lg bg-amber-50 text-amber-800 text-sm border border-amber-100">
                {sentimentError}
              </div>
            )}

            {sentiment ? (
              <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-2">
                <div className="bg-[var(--bg-surface-muted)] rounded-lg p-3 flex items-center justify-between">
                  <div className="text-xs text-gray-500">综合</div>
                  <span className={`px-2 py-0.5 text-xs rounded-md border ${sentimentLabel(sentiment.overall_sentiment).cls}`}>
                    {sentimentLabel(sentiment.overall_sentiment).label}
                  </span>
                </div>
                <div className="bg-[var(--bg-surface-muted)] rounded-lg p-3 flex items-center justify-between">
                  <div className="text-xs text-gray-500">正面</div>
                  <div className="font-mono font-semibold text-emerald-700">{sentiment.positive_count}</div>
                </div>
                <div className="bg-[var(--bg-surface-muted)] rounded-lg p-3 flex items-center justify-between">
                  <div className="text-xs text-gray-500">中性</div>
                  <div className="font-mono font-semibold text-gray-700">{sentiment.neutral_count}</div>
                </div>
                <div className="bg-[var(--bg-surface-muted)] rounded-lg p-3 flex items-center justify-between">
                  <div className="text-xs text-gray-500">负面</div>
                  <div className="font-mono font-semibold text-red-700">{sentiment.negative_count}</div>
                </div>
                <div className="md:col-span-4 text-xs text-gray-500">
                  新闻样本：{sentiment.news_count} 条（仅用于辅助判断，非投资建议）
                </div>
              </div>
            ) : (
              <div className="mt-3 text-sm text-gray-500">未分析或暂无结果。</div>
            )}
          </Section>

          <Section title="公司公告" open={openSections.notices} onToggle={() => toggleSection("notices")}>
            <div className="flex items-center justify-end">
              <button type="button" onClick={() => fetchNotices(true)} disabled={noticesLoading} className="text-xs text-gray-500 hover:text-gray-800">
                刷新
              </button>
            </div>
            {!!noticesError && (
              <div role="alert" className="mt-2 p-3 rounded-lg bg-amber-50 text-amber-800 text-sm border border-amber-100">
                {noticesError}
              </div>
            )}
            <div className="mt-3 space-y-2">
              {noticesLoading ? (
                <div className="text-sm text-gray-500">加载公告中...</div>
              ) : notices.length > 0 ? (
                notices.map((n, i) => (
                  <a
                    key={`${n.notice_date || ""}-${i}`}
                    href={String(n.url || "#")}
                    target="_blank"
                    rel="noreferrer"
                    className="block p-3 rounded-lg border hover:bg-[var(--bg-surface-muted)] transition-colors"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-900 truncate">{String(n.title || "")}</div>
                        <div className="mt-1 text-xs text-gray-500 flex items-center gap-2">
                          <span>{String(n.notice_date || "-")}</span>
                          {n.notice_type ? <span className="px-2 py-0.5 rounded bg-gray-100 text-gray-700">{String(n.notice_type)}</span> : null}
                        </div>
                      </div>
                      <span className="text-xs text-gray-400">打开</span>
                    </div>
                  </a>
                ))
              ) : (
                <div className="text-sm text-gray-500">暂无公告数据。</div>
              )}
            </div>
          </Section>

          <Section title="研报/机构观点" open={openSections.reports} onToggle={() => toggleSection("reports")}>
            <div className="flex items-center justify-end">
              <button type="button" onClick={() => fetchReports(true)} disabled={reportsLoading} className="text-xs text-gray-500 hover:text-gray-800">
                刷新
              </button>
            </div>
            {!!reportsError && (
              <div role="alert" className="mt-2 p-3 rounded-lg bg-amber-50 text-amber-800 text-sm border border-amber-100">
                {reportsError}
              </div>
            )}
            <div className="mt-3 space-y-2">
              {reportsLoading ? (
                <div className="text-sm text-gray-500">加载研报中...</div>
              ) : reports.length > 0 ? (
                reports.map((r, i) => (
                  <a
                    key={`${r.publish_date || ""}-${i}`}
                    href={String(r.url || "#")}
                    target="_blank"
                    rel="noreferrer"
                    className="block p-3 rounded-lg border hover:bg-[var(--bg-surface-muted)] transition-colors"
                  >
                    <div className="text-sm font-medium text-gray-900">{String(r.title || "")}</div>
                    <div className="mt-1 text-xs text-gray-500 flex flex-wrap items-center gap-2">
                      <span>{String(r.publish_date || "-")}</span>
                      {r.org_name ? <span>{String(r.org_name)}</span> : null}
                      {r.rating ? <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700">{String(r.rating)}</span> : null}
                      {typeof r.target_price === "number" && Number.isFinite(r.target_price) ? (
                        <span className="font-mono">目标价 {r.target_price.toFixed(2)}</span>
                      ) : null}
                    </div>
                  </a>
                ))
              ) : (
                <div className="text-sm text-gray-500">暂无研报数据。</div>
              )}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Point({ label, value, cls = "" }: { label: string; value: string; cls?: string }) {
  return (
    <div className="bg-[var(--bg-surface-muted)] rounded-lg p-3 flex items-center justify-between gap-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`font-mono font-semibold ${cls}`}>{value}</div>
    </div>
  );
}

function Section({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full px-4 py-3 flex items-center justify-between bg-[var(--bg-surface-muted)] hover:bg-[var(--bg-surface)] transition-colors"
      >
        <div className="text-sm font-medium text-gray-900">{title}</div>
        <div className="text-xs text-gray-500">{open ? "收起" : "展开"}</div>
      </button>
      {open ? <div className="p-4">{children}</div> : null}
    </div>
  );
}
