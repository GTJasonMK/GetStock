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

export default function StocksPanel({ active = true }: { active?: boolean }) {
  const toast = useToast();
  const [stocks, setStocks] = useState<any[]>([]);
  const [quotes, setQuotes] = useState<Record<string, StockQuote>>({});
  const [loading, setLoading] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchActiveIndex, setSearchActiveIndex] = useState(0);
  const [selectedStock, setSelectedStock] = useState<string | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const dedupeWarnedRef = useRef(false);

  // 分组相关状态
  const [groups, setGroups] = useState<any[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<number | null>(null);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");

  const [removeStockConfirm, setRemoveStockConfirm] = useState<{ code: string; name?: string } | null>(null);
  const [deleteGroupConfirm, setDeleteGroupConfirm] = useState<{ id: number; name: string } | null>(null);

  // 获取分组
  const fetchGroups = useCallback(async () => {
    try {
      const data = await api.getGroups();
      setGroups(data || []);
    } catch { /* ignore */ }
  }, []);

  const fetchStocks = useCallback(async () => {
    try {
      // 后端 /stock/follow 返回数组 (Response[List[FollowedStockResponse]])
      const data = await api.getFollowedStocks();
      const rawList = Array.isArray(data) ? data : [];

      // 去重：避免后端/导入产生重复 code，导致 React key 冲突
      const uniq = new Map<string, any>();
      for (const s of rawList) {
        const code = String(s?.stock_code || "").trim();
        if (!code) continue;
        if (!uniq.has(code)) uniq.set(code, s);
      }
      const stockList = Array.from(uniq.values());
      if (rawList.length !== stockList.length) {
        if (!dedupeWarnedRef.current) {
          dedupeWarnedRef.current = true;
          toast.push({ variant: "warning", title: "数据异常", message: "自选股列表存在重复代码，已在前端自动去重显示。" });
        }
      }

      setStocks(stockList);
      if (stockList.length > 0) {
        const codes = stockList.map((s: any) => s.stock_code);
        // 后端返回 {quotes: [...]}，字段为 stock_code/current_price/...
        const quotesData = await api.getRealtimeQuotes(codes);
        const quotesMap: Record<string, StockQuote> = {};
        (quotesData.quotes || []).forEach((q: StockQuote) => { quotesMap[q.stock_code] = q; });
        setQuotes(quotesMap);
      }
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | undefined;

    const start = async () => {
      // 先尝试用缓存快速回填（页面切换/返回不再“空白等待”）
      try {
        const cachedGroups = api.peekCache<any>(endpoints.group.list());
        if (Array.isArray(cachedGroups) && cachedGroups.length > 0) setGroups(cachedGroups);
      } catch { /* ignore */ }

      try {
        const cachedFollow = api.peekCache<any>(endpoints.stock.followed());
        const rawList = Array.isArray(cachedFollow) ? cachedFollow : [];
        if (rawList.length > 0) {
          const uniq = new Map<string, any>();
          for (const s of rawList) {
            const code = String(s?.stock_code || "").trim();
            if (!code) continue;
            if (!uniq.has(code)) uniq.set(code, s);
          }
          const stockList = Array.from(uniq.values());
          setStocks(stockList);
          setLoading(false);

          // 行情也尝试回填（若命中缓存则瞬时展示价格/涨跌幅）
          const codes = stockList.map((s: any) => s.stock_code);
          const cachedQuotes = api.peekCache<any>(endpoints.stock.realtime(codes));
          if (cachedQuotes && Array.isArray(cachedQuotes.quotes)) {
            const quotesMap: Record<string, StockQuote> = {};
            (cachedQuotes.quotes || []).forEach((q: StockQuote) => { quotesMap[q.stock_code] = q; });
            setQuotes(quotesMap);
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

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    try {
      const results = await api.searchStock(searchKeyword);
      const list = results || [];
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

  const handleRemove = async (code: string, name?: string) => {
    try {
      await api.removeFollowStock(code);
      fetchStocks();
      toast.push({ variant: "success", title: "已移除", message: name ? `${name}（${code}）已移除` : `${code} 已移除` });
    } catch { /* ignore */ }
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
        const group = groups.find((g: any) => g.id === selectedGroup);
        return group?.stocks?.some((gs: any) => gs.stock_code === s.stock_code);
      })
    : stocks;

  const selectedStockInfo = selectedStock ? stocks.find((s: any) => s.stock_code === selectedStock) : null;

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
          {groups.map((group: any) => (
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
        </div>

        {/* 股票列表 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-center text-gray-400">加载中...</div>
          ) : filteredStocks.length === 0 ? (
            <div className="p-4 text-center text-gray-400">
              {selectedGroup ? "该分组暂无股票" : "暂无自选股"}
            </div>
          ) : (
            filteredStocks.map((stock) => {
              const quote = quotes[stock.stock_code];
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
                    </div>
                  </div>
                  {/* 分组操作 */}
                  {groups.length > 0 && (
                    <div className="mt-2 flex gap-1 flex-wrap">
                      {groups.map((group: any) => {
                        const inGroup = group.stocks?.some((gs: any) => gs.stock_code === stock.stock_code);
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
              onRemove={() => {
                setRemoveStockConfirm({ code: selectedStock, name: selectedStockInfo?.stock_name });
              }}
            />
            <KLineChart code={selectedStock} />
            <StockMinuteChart code={selectedStock} />
            <StockMoneyFlowChart code={selectedStock} />
            <ChipDistributionChart code={selectedStock} />
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
