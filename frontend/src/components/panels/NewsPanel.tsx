"use client";

import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";

type NewsTab = "latest" | "search" | "telegraph" | "global" | "tradingview";

export default function NewsPanel() {
  const [tab, setTab] = useState<NewsTab>("latest");
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState<string>("");
  const [engines, setEngines] = useState<any[]>([]);
  const [selectedEngine, setSelectedEngine] = useState<string>(""); // "" 表示自动
  const [resolvedEngine, setResolvedEngine] = useState<string>("");

  // 最新资讯
  const [latestSource, setLatestSource] = useState<string>(""); // ""=自动
  const [latestItems, setLatestItems] = useState<any[]>([]);
  const [latestLoading, setLatestLoading] = useState(false);
  const [latestError, setLatestError] = useState<string>("");

  // 快讯相关
  const [telegraphItems, setTelegraphItems] = useState<any[]>([]);
  const [telegraphPage, setTelegraphPage] = useState(1);
  const [telegraphLoading, setTelegraphLoading] = useState(false);
  const [telegraphMeta, setTelegraphMeta] = useState<{ source?: string; notice?: string } | null>(null);
  const [telegraphError, setTelegraphError] = useState<string>("");

  // 全球指数
  const [globalIndexes, setGlobalIndexes] = useState<any[]>([]);
  const [globalLoading, setGlobalLoading] = useState(false);

  // TradingView
  const [tvItems, setTvItems] = useState<any[]>([]);
  const [tvLoading, setTvLoading] = useState(false);
  const [tvError, setTvError] = useState<string>("");

  // 搜索引擎列表
  useEffect(() => {
    api.getSearchEngines().then((data) => setEngines(data.engines || [])).catch(() => {});
  }, []);

  // 获取最新资讯
  const fetchLatest = useCallback(async () => {
    setLatestLoading(true);
    setLatestError("");
    try {
      const data = await api.getLatestNews(latestSource || undefined, 30);
      setLatestItems(data?.items || []);
    } catch (e: any) {
      setLatestItems([]);
      setLatestError(e?.message || "获取最新资讯失败");
    }
    setLatestLoading(false);
  }, [latestSource]);

  // 获取快讯
  const fetchTelegraph = useCallback(async (page: number) => {
    setTelegraphLoading(true);
    if (page === 1) {
      setTelegraphError("");
      setTelegraphMeta(null);
    }
    try {
      const data = await api.getTelegraph(page, 30);
      setTelegraphMeta({ source: data?.source, notice: data?.notice });
      if (page === 1) {
        setTelegraphItems(data?.items || []);
      } else {
        setTelegraphItems((prev) => [...prev, ...(data?.items || [])]);
      }
    } catch (e: any) {
      setTelegraphError(e?.message || "获取快讯失败");
      if (page === 1) setTelegraphItems([]);
    }
    setTelegraphLoading(false);
  }, []);

  // 获取全球指数
  const fetchGlobalIndexes = useCallback(async () => {
    setGlobalLoading(true);
    try {
      // 后端 GlobalIndexResponse 字段为 indexes，字段包含 code/name/current/change_percent/change_amount/update_time
      const data = await api.getGlobalIndexes();
      // 映射字段名到前端期望的格式
      const indexes = (data?.indexes || []).map((item: any) => ({
        code: item.code,
        name: item.name,
        price: item.current,
        change: item.change_amount,
        change_percent: item.change_percent,
        update_time: item.update_time,
      }));
      setGlobalIndexes(indexes);
    } catch { /* ignore */ }
    setGlobalLoading(false);
  }, []);

  const fetchTradingView = useCallback(async () => {
    setTvLoading(true);
    setTvError("");
    try {
      const data = await api.getTradingViewNews(30);
      setTvItems(data?.items || []);
    } catch (e: any) {
      setTvItems([]);
      setTvError(e?.message || "获取 TradingView 资讯失败");
    }
    setTvLoading(false);
  }, []);

  // tab切换时加载数据
  useEffect(() => {
    if (tab === "latest") {
      fetchLatest();
    } else if (tab === "telegraph") {
      setTelegraphPage(1);
      fetchTelegraph(1);
    } else if (tab === "global") {
      fetchGlobalIndexes();
    } else if (tab === "tradingview") {
      fetchTradingView();
    }
  }, [tab, fetchLatest, fetchTelegraph, fetchGlobalIndexes, fetchTradingView]);

  const handleSearch = async () => {
    if (!keyword.trim()) return;
    setLoading(true);
    setSearchError("");
    try {
      const data = await api.searchNews(keyword, selectedEngine || undefined);
      setResults(data.items || []);
      setResolvedEngine(data.engine || "");
    } catch (e: any) {
      setResults([]);
      setResolvedEngine("");
      setSearchError(e?.message || "搜索失败");
    }
    setLoading(false);
  };

  const handleLoadMoreTelegraph = () => {
    const nextPage = telegraphPage + 1;
    setTelegraphPage(nextPage);
    fetchTelegraph(nextPage);
  };

  const formatChange = (v: number | null | undefined) => v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
  const changeColor = (v: number | null | undefined) => v == null ? "text-gray-500" : v > 0 ? "text-red-600" : v < 0 ? "text-green-600" : "text-gray-500";

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">资讯中心</h1>

      {/* Tab */}
      <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
        {[
          { key: "latest", label: "最新" },
          { key: "telegraph", label: "快讯" },
          { key: "global", label: "全球指数" },
          { key: "tradingview", label: "TradingView" },
          { key: "search", label: "搜索" },
        ].map((t) => (
          <button
            type="button"
            key={t.key}
            onClick={() => setTab(t.key as NewsTab)}
            className={`px-4 py-2 text-sm rounded-md transition-colors ${tab === t.key ? "bg-white shadow text-blue-600" : "text-gray-600 hover:text-gray-900"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 最新资讯 */}
      {tab === "latest" && (
        <div>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-2">
              <select
                value={latestSource}
                onChange={(e) => setLatestSource(e.target.value)}
                className="px-3 py-2 border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                title="选择资讯来源"
              >
                <option value="">自动</option>
                <option value="cls">cls</option>
                <option value="sina">sina</option>
              </select>
              <div className="text-xs text-gray-400">默认拉取 30 条</div>
            </div>
            <button
              type="button"
              onClick={fetchLatest}
              className="px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
            >
              刷新
            </button>
          </div>

          {latestError && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm">
              <div className="font-medium mb-1">最新资讯获取失败</div>
              <div className="text-red-700/80 break-words">{latestError}</div>
              <div className="mt-2">
                <button
                  type="button"
                  onClick={fetchLatest}
                  className="px-3 py-1.5 text-sm rounded-md bg-white border border-red-200 hover:bg-red-50"
                >
                  重试
                </button>
              </div>
            </div>
          )}

          {latestLoading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : latestItems.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无最新资讯</div>
          ) : (
            <div className="space-y-3">
              {latestItems.map((item, i) => (
                <a
                  key={item.news_id || item.url || i}
                  href={item.url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block bg-white rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between gap-4">
                    <h3 className="font-medium text-blue-600 hover:underline min-w-0 line-clamp-2">{item.title}</h3>
                    {item.source && (
                      <span className="shrink-0 text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-md font-mono">
                        {item.source}
                      </span>
                    )}
                  </div>
                  {item.content && <p className="text-sm text-gray-600 mt-2 line-clamp-2">{item.content}</p>}
                  {item.publish_time && (
                    <div className="text-xs text-gray-400 mt-2">{new Date(item.publish_time).toLocaleString()}</div>
                  )}
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 快讯 */}
      {tab === "telegraph" && (
        <div>
          {(telegraphError || telegraphMeta?.notice) && (
            <div className="space-y-2 mb-4">
              {telegraphError && (
                <div className="bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="font-medium">快讯获取失败</div>
                    <div className="text-red-700/80 break-words">{telegraphError}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setTelegraphPage(1);
                      fetchTelegraph(1);
                    }}
                    className="shrink-0 px-3 py-1.5 text-sm rounded-md bg-white border border-red-200 hover:bg-red-50"
                  >
                    重试
                  </button>
                </div>
              )}

              {telegraphMeta?.notice && (
                <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <div className="font-medium">快讯来源提示</div>
                      <div className="text-amber-800/80 break-words">{telegraphMeta.notice}</div>
                    </div>
                    {telegraphMeta?.source && (
                      <div className="shrink-0 text-xs text-amber-700 bg-white/60 border border-amber-200 rounded-md px-2 py-1 font-mono">
                        {telegraphMeta.source}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {telegraphLoading && telegraphItems.length === 0 ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : telegraphItems.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无快讯数据</div>
          ) : (
            <div className="space-y-0">
              {telegraphItems.map((item, i) => (
                <div key={item.telegraph_id || i} className="flex gap-4 py-3 border-b border-gray-100">
                  {/* 时间线 */}
                  <div className="flex flex-col items-center w-20 flex-shrink-0">
                    <span className="text-sm text-gray-400">
                      {item.publish_time ? new Date(item.publish_time).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                    <div className="w-2 h-2 rounded-full bg-blue-400 mt-1" />
                  </div>
                  {/* 内容 */}
                  <div className="flex-1 min-w-0">
                    {item.title && (
                      <div className="font-medium text-sm mb-1">{item.title}</div>
                    )}
                    <div className="text-sm text-gray-600 leading-relaxed">{item.content}</div>
                    {item.source && (
                      <div className="text-xs text-gray-400 mt-1">{item.source}</div>
                    )}
                  </div>
                </div>
              ))}
              <div className="text-center py-4">
                <button
                  type="button"
                  onClick={handleLoadMoreTelegraph}
                  disabled={telegraphLoading}
                  className="px-6 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg disabled:opacity-50"
                >
                  {telegraphLoading ? "加载中..." : "加载更多"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 全球指数 */}
      {tab === "global" && (
        <div>
          {globalLoading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : globalIndexes.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无全球指数数据</div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {globalIndexes.map((item, i) => (
                <div key={item.code || i} className="bg-white rounded-xl p-4 shadow-sm">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <div className="font-medium">{item.name}</div>
                      <div className="text-xs text-gray-400">{item.code}</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-xl font-bold font-mono ${changeColor(item.change_percent)}`}>
                        {typeof item.price === "number" ? item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : item.price || "-"}
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <div className={`text-sm font-mono ${changeColor(item.change_percent)}`}>
                      {typeof item.change === "number" ? (item.change > 0 ? "+" : "") + item.change.toFixed(2) : "-"}
                    </div>
                    <div className={`text-sm font-mono font-medium ${changeColor(item.change_percent)}`}>
                      {formatChange(item.change_percent)}
                    </div>
                  </div>
                  {item.update_time && (
                    <div className="text-xs text-gray-400 mt-2">{item.update_time}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TradingView */}
      {tab === "tradingview" && (
        <div>
          <div className="flex items-center justify-between gap-2 mb-4">
            <div className="text-sm text-gray-600">TradingView 资讯（30 条）</div>
            <button
              type="button"
              onClick={fetchTradingView}
              className="px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
            >
              刷新
            </button>
          </div>

          {tvError && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm">
              <div className="font-medium mb-1">TradingView 获取失败</div>
              <div className="text-red-700/80 break-words">{tvError}</div>
            </div>
          )}

          {tvLoading ? (
            <div className="text-center py-12 text-gray-400">加载中...</div>
          ) : tvItems.length === 0 ? (
            <div className="text-center py-12 text-gray-400">暂无 TradingView 资讯</div>
          ) : (
            <div className="space-y-3">
              {tvItems.map((item, i) => (
                <a
                  key={item.id || item.url || i}
                  href={item.url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block bg-white rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between gap-4">
                    <h3 className="font-medium text-blue-600 hover:underline min-w-0 line-clamp-2">{item.title}</h3>
                    {item.source && (
                      <span className="shrink-0 text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-md font-mono">
                        {item.source}
                      </span>
                    )}
                  </div>
                  {item.published_at && (
                    <div className="text-xs text-gray-400 mt-2">{new Date(item.published_at).toLocaleString()}</div>
                  )}
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 搜索 */}
      {tab === "search" && (
        <div>
          <div className="flex flex-wrap gap-2 mb-6 items-center">
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="输入关键词搜索新闻..."
              className="flex-1 max-w-lg px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />

            <select
              value={selectedEngine}
              onChange={(e) => setSelectedEngine(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              title="选择搜索引擎"
            >
              <option value="">自动</option>
              <option value="bocha">bocha</option>
              <option value="tavily">tavily</option>
              <option value="serpapi">serpapi</option>
            </select>

            <button type="button" onClick={handleSearch} disabled={loading} className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
              {loading ? "搜索中..." : "搜索"}
            </button>
          </div>

          {/* 搜索引擎状态 */}
          <div className="flex gap-4 mb-6">
            {engines.map((e) => (
              <div key={e.engine} className="flex items-center gap-2 text-sm text-gray-500">
                <span className={`w-2 h-2 rounded-full ${e.enabled_keys > 0 ? "bg-green-500" : "bg-gray-300"}`} />
                <span>{e.engine}</span>
                <span className="text-gray-400">({e.enabled_keys} keys)</span>
              </div>
            ))}
          </div>

          {engines.length > 0 && engines.every((e) => (e.enabled_keys || 0) <= 0) && (
            <div className="mb-6 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg px-4 py-3 text-sm">
              当前未配置可用的搜索引擎 Key，可能导致搜索结果为空。可在「设置 → 搜索引擎」查看状态，并通过接口添加 Key 后重试。
            </div>
          )}

          {searchError && (
            <div className="mb-6 bg-red-50 border border-red-200 text-red-800 rounded-lg px-4 py-3 text-sm">
              <div className="font-medium mb-1">搜索失败</div>
              <div className="text-red-700/80 break-words">{searchError}</div>
              <div className="mt-2">
                <button
                  type="button"
                  onClick={handleSearch}
                  className="px-3 py-1.5 text-sm rounded-md bg-white border border-red-200 hover:bg-red-50"
                >
                  重试
                </button>
              </div>
            </div>
          )}

          {/* 搜索结果 */}
          {results.length > 0 && (
            <div className="space-y-4">
              {(resolvedEngine || selectedEngine) && (
                <div className="text-sm text-gray-500">
                  本次结果来源：<span className="font-mono">{resolvedEngine || selectedEngine || "auto"}</span>
                </div>
              )}
              {results.map((item, i) => (
                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer" className="block bg-white rounded-xl p-4 shadow-sm hover:shadow-md transition-shadow">
                  <h3 className="font-medium text-blue-600 hover:underline mb-2">{item.title}</h3>
                  <p className="text-sm text-gray-600 line-clamp-2">{item.content}</p>
                  <div className="flex gap-4 mt-2 text-xs text-gray-400">
                    <span>{item.source}</span>
                    {item.publish_time && <span>{new Date(item.publish_time).toLocaleString()}</span>}
                  </div>
                </a>
              ))}
            </div>
          )}

          {results.length === 0 && !loading && keyword.trim() && !searchError && (
            <div className="text-center py-12 text-gray-400">暂无搜索结果</div>
          )}
        </div>
      )}
    </div>
  );
}
