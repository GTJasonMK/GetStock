"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/ToastProvider";

type FundListItem = {
  fund_code: string;
  fund_name: string;
  fund_type?: string;
  nav?: number | null;
  nav_change?: number | null;
  return_1m?: number | null;
  return_3m?: number | null;
  return_6m?: number | null;
  return_1y?: number | null;
  manager?: string;
  fund_scale?: number | null;
};

type FundSearchResult = {
  fund_code: string;
  fund_name: string;
  fund_type?: string;
};

type FundReturns = {
  week_1?: number | null;
  month_1?: number | null;
  month_3?: number | null;
  month_6?: number | null;
  year_1?: number | null;
  year_3?: number | null;
  since_establish?: number | null;
};

type FundDetail = {
  fund_code: string;
  fund_name: string;
  fund_type?: string;
  nav?: number | null;
  nav_change?: number | null;
  acc_nav?: number | null;
  return_1w?: number | null;
  return_1m?: number | null;
  return_3m?: number | null;
  return_6m?: number | null;
  return_1y?: number | null;
  return_3y?: number | null;
  returns?: FundReturns;
  establish_date?: string;
  fund_scale?: number | null;
  manager?: string;
  management_fee?: number | null;
  custody_fee?: number | null;
  fund_company?: string;
  custodian_bank?: string;
};

function toNumberOrNull(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function toStringOrUndefined(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function normalizeFundReturns(raw: unknown): FundReturns | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const obj = raw as Record<string, unknown>;
  return {
    week_1: toNumberOrNull(obj.week_1),
    month_1: toNumberOrNull(obj.month_1),
    month_3: toNumberOrNull(obj.month_3),
    month_6: toNumberOrNull(obj.month_6),
    year_1: toNumberOrNull(obj.year_1),
    year_3: toNumberOrNull(obj.year_3),
    since_establish: toNumberOrNull(obj.since_establish),
  };
}

function normalizeFundListItem(raw: unknown): FundListItem | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const fundCode = toStringOrUndefined(obj.fund_code);
  if (!fundCode) return null;

  const fundName =
    toStringOrUndefined(obj.fund_name) ||
    toStringOrUndefined(obj.name) ||
    fundCode;

  return {
    fund_code: fundCode,
    fund_name: fundName,
    fund_type: toStringOrUndefined(obj.fund_type),
    nav: toNumberOrNull(obj.nav),
    nav_change: toNumberOrNull(obj.nav_change),
    return_1m: toNumberOrNull(obj.return_1m),
    return_3m: toNumberOrNull(obj.return_3m),
    return_6m: toNumberOrNull(obj.return_6m),
    return_1y: toNumberOrNull(obj.return_1y),
    manager: toStringOrUndefined(obj.manager),
    fund_scale: toNumberOrNull(obj.fund_scale),
  };
}

function normalizeFundSearchItem(raw: unknown): FundSearchResult | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const fundCode = toStringOrUndefined(obj.fund_code);
  const fundName = toStringOrUndefined(obj.fund_name);
  if (!fundCode || !fundName) return null;

  return {
    fund_code: fundCode,
    fund_name: fundName,
    fund_type: toStringOrUndefined(obj.fund_type),
  };
}

function normalizeFundDetail(raw: unknown, fallback: FundListItem): FundDetail {
  if (!raw || typeof raw !== "object") {
    return {
      fund_code: fallback.fund_code,
      fund_name: fallback.fund_name,
      fund_type: fallback.fund_type,
      nav: fallback.nav,
      nav_change: fallback.nav_change,
      return_1m: fallback.return_1m,
      return_3m: fallback.return_3m,
      return_6m: fallback.return_6m,
      return_1y: fallback.return_1y,
      manager: fallback.manager,
      fund_scale: fallback.fund_scale,
    };
  }

  const obj = raw as Record<string, unknown>;
  return {
    fund_code: toStringOrUndefined(obj.fund_code) || fallback.fund_code,
    fund_name:
      toStringOrUndefined(obj.fund_name) ||
      toStringOrUndefined(obj.name) ||
      fallback.fund_name,
    fund_type: toStringOrUndefined(obj.fund_type) || fallback.fund_type,
    nav: toNumberOrNull(obj.nav) ?? toNumberOrNull(obj.net_value) ?? fallback.nav,
    nav_change: toNumberOrNull(obj.nav_change) ?? toNumberOrNull(obj.day_growth) ?? fallback.nav_change,
    acc_nav: toNumberOrNull(obj.acc_nav) ?? toNumberOrNull(obj.total_value),
    return_1w: toNumberOrNull(obj.return_1w) ?? toNumberOrNull(obj.week_growth),
    return_1m: toNumberOrNull(obj.return_1m) ?? toNumberOrNull(obj.month_growth) ?? fallback.return_1m,
    return_3m: toNumberOrNull(obj.return_3m) ?? toNumberOrNull(obj.three_month_growth) ?? fallback.return_3m,
    return_6m: toNumberOrNull(obj.return_6m) ?? toNumberOrNull(obj.six_month_growth) ?? fallback.return_6m,
    return_1y: toNumberOrNull(obj.return_1y) ?? toNumberOrNull(obj.year_growth) ?? fallback.return_1y,
    return_3y: toNumberOrNull(obj.return_3y),
    returns: normalizeFundReturns(obj.returns),
    establish_date: toStringOrUndefined(obj.establish_date),
    fund_scale: toNumberOrNull(obj.fund_scale) ?? fallback.fund_scale,
    manager: toStringOrUndefined(obj.manager) || fallback.manager,
    management_fee: toNumberOrNull(obj.management_fee),
    custody_fee: toNumberOrNull(obj.custody_fee),
    fund_company: toStringOrUndefined(obj.fund_company) || toStringOrUndefined(obj.company),
    custodian_bank: toStringOrUndefined(obj.custodian_bank),
  };
}

export default function FundsPanel() {
  const toast = useToast();
  const [funds, setFunds] = useState<FundListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [searchResults, setSearchResults] = useState<FundSearchResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchActiveIndex, setSearchActiveIndex] = useState(0);
  const searchRef = useRef<HTMLDivElement>(null);
  const [selectedFund, setSelectedFund] = useState<string | null>(null);
  const [fundDetail, setFundDetail] = useState<FundDetail | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  const [removeFundConfirm, setRemoveFundConfirm] = useState<{ code: string; name?: string } | null>(null);

  const fetchFunds = useCallback(async () => {
    try {
      const data = await api.getFollowedFunds();
      const list = (Array.isArray(data) ? data : [])
        .map(normalizeFundListItem)
        .filter((item): item is FundListItem => item !== null);
      setFunds(list);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFunds();
  }, [fetchFunds]);

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
    if (!showDetailModal) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      setShowDetailModal(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showDetailModal]);

  const handleSearch = async () => {
    if (!searchKeyword.trim()) return;
    try {
      // 后端 FundSearchResponse 字段为 results，不是 items
      const results = await api.searchFunds(searchKeyword);
      const list = (Array.isArray(results?.results) ? results.results : [])
        .map(normalizeFundSearchItem)
        .filter((item): item is FundSearchResult => item !== null);
      setSearchResults(list);
      setSearchOpen(list.length > 0);
      setSearchActiveIndex(0);
    } catch {
      // ignore
    }
  };

  const handleAdd = async (code: string, name: string, fundType?: string) => {
    try {
      await api.addFollowedFund(code, name, fundType);
      setSearchResults([]);
      setSearchOpen(false);
      setSearchKeyword("");
      fetchFunds();
      toast.push({ variant: "success", title: "已添加", message: `${name}（${code}）已加入关注` });
    } catch {
      // ignore
    }
  };

  const handleRemove = async (code: string, name?: string) => {
    try {
      await api.removeFollowedFund(code);
      if (selectedFund === code) {
        setSelectedFund(null);
        setShowDetailModal(false);
      }
      fetchFunds();
      toast.push({ variant: "success", title: "已移除", message: name ? `${name}（${code}）已移除` : `${code} 已移除` });
    } catch {
      // ignore
    }
  };

  const handleCardClick = async (fund: FundListItem) => {
    setSelectedFund(fund.fund_code);
    try {
      const detail = await api.getFundDetail(fund.fund_code);
      setFundDetail(normalizeFundDetail(detail, fund));
      setShowDetailModal(true);
    } catch {
      // ignore
    }
  };

  const formatChange = (v: number | null | undefined) => (v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
  const changeColor = (v: number | null | undefined) => (v == null ? "text-gray-500" : v > 0 ? "text-red-600" : v < 0 ? "text-green-600" : "text-gray-500");
  const changeBg = (v: number | null | undefined) => (v == null ? "bg-gray-50" : v > 0 ? "bg-red-50" : v < 0 ? "bg-green-50" : "bg-gray-50");

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">基金持仓</h1>
        <div className="flex gap-2">
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
                    if (item) handleAdd(item.fund_code, item.fund_name, item.fund_type);
                    return;
                  }
                  handleSearch();
                }
              }}
              placeholder="搜索基金..."
              className="input w-64 pl-9"
              role="combobox"
              aria-autocomplete="list"
              aria-haspopup="listbox"
              aria-label="搜索基金"
              aria-expanded={searchOpen && searchResults.length > 0}
              aria-controls="fund-search-results"
              aria-activedescendant={searchOpen ? `fund-search-option-${searchActiveIndex}` : undefined}
            />
            <svg className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            {searchOpen && searchResults.length > 0 && (
              <div
                id="fund-search-results"
                role="listbox"
                className="absolute z-10 mt-1 w-full bg-white border border-[color:var(--border-color)] rounded-lg shadow-lg max-h-64 overflow-y-auto"
              >
                {searchResults.map((item, idx) => {
                  const active = idx === searchActiveIndex;
                  return (
                    <div
                      key={item.fund_code}
                      id={`fund-search-option-${idx}`}
                      role="option"
                      aria-selected={active}
                      onMouseEnter={() => setSearchActiveIndex(idx)}
                      onClick={() => handleAdd(item.fund_code, item.fund_name, item.fund_type)}
                      className={`px-4 py-3 cursor-pointer border-b last:border-b-0 transition-colors duration-200 ${
                        active ? "bg-[var(--bg-surface-muted)]" : "hover:bg-[var(--bg-surface-muted)]"
                      }`}
                    >
                      <div className="font-medium text-sm">{item.fund_name}</div>
                      <div className="text-xs text-[var(--text-muted)] mt-0.5 flex items-center gap-2">
                        <span className="font-mono">{item.fund_code}</span>
                        {item.fund_type && (
                          <span className="px-1.5 py-0.5 rounded bg-[var(--bg-surface-muted)] text-[var(--text-muted)]">
                            {item.fund_type}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          <button type="button" onClick={handleSearch} className="btn btn-primary text-sm">
            搜索
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中...</div>
      ) : funds.length === 0 ? (
        <div className="card p-12 text-center">
          <svg className="w-12 h-12 mx-auto text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-gray-400">暂无关注基金，搜索添加您关注的基金</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {funds.map((fund) => (
            <div
              key={fund.fund_code}
              onClick={() => handleCardClick(fund)}
              className="card p-4 hover:shadow-md hover:border-[color:var(--accent-hover)] transition-shadow duration-200 cursor-pointer"
            >
              {/* 基金头部 */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{fund.fund_name}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-gray-400">{fund.fund_code}</span>
                    {fund.fund_type && (
                      <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded">{fund.fund_type}</span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setRemoveFundConfirm({ code: fund.fund_code, name: fund.fund_name });
                  }}
                  className="icon-btn p-1 text-gray-300 hover:text-red-500 transition-colors"
                  title="移除"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* 净值信息 */}
              <div className="flex items-end justify-between mb-3">
                <div>
                  <div className={`text-2xl font-bold font-mono ${changeColor(fund.nav_change)}`}>
                    {typeof fund.nav === "number" ? fund.nav.toFixed(4) : "-"}
                  </div>
                  <div className="text-xs text-gray-400">单位净值</div>
                </div>
                <div className={`px-3 py-1.5 rounded-lg ${changeBg(fund.nav_change)}`}>
                  <div className={`text-lg font-bold font-mono ${changeColor(fund.nav_change)}`}>
                    {formatChange(fund.nav_change)}
                  </div>
                  <div className="text-xs text-gray-400 text-right">日涨跌</div>
                </div>
              </div>

              {/* 收益率 */}
              <div className="grid grid-cols-4 gap-2 pt-3 border-t">
                {[
                  { label: "近1月", value: fund.return_1m },
                  { label: "近3月", value: fund.return_3m },
                  { label: "近6月", value: fund.return_6m },
                  { label: "近1年", value: fund.return_1y },
                ].map((item) => (
                  <div key={item.label} className="text-center">
                    <div className={`text-sm font-mono font-medium ${changeColor(item.value)}`}>
                      {formatChange(item.value)}
                    </div>
                    <div className="text-xs text-gray-400">{item.label}</div>
                  </div>
                ))}
              </div>

              {/* 基金经理和规模 */}
              {(fund.manager || fund.fund_scale) && (
                <div className="flex justify-between items-center mt-3 pt-3 border-t text-xs text-gray-400">
                  {fund.manager && <span>经理: {fund.manager}</span>}
                  {typeof fund.fund_scale === "number" && <span>规模: {(fund.fund_scale / 1e8).toFixed(2)}亿</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 基金详情弹窗 */}
      {showDetailModal && fundDetail && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setShowDetailModal(false)}>
          <div className="card bg-white w-full max-w-[720px] max-h-[90vh] overflow-y-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            {/* 头部 */}
            <div className="p-6 border-b">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold">{fundDetail.fund_name}</h2>
                  <div className="text-gray-500 mt-1">{fundDetail.fund_code} | {fundDetail.fund_type || "基金"}</div>
                </div>
                <button type="button" onClick={() => setShowDetailModal(false)} className="icon-btn -mr-2 -mt-2 text-gray-400 hover:text-gray-600" aria-label="关闭">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="grid grid-cols-4 gap-4 mt-4">
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <div className={`text-xl font-bold ${changeColor(fundDetail.nav_change)}`}>{typeof fundDetail.nav === "number" ? fundDetail.nav.toFixed(4) : "-"}</div>
                  <div className="text-gray-500 text-xs mt-1">单位净值</div>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <div className={`text-xl font-bold ${changeColor(fundDetail.nav_change)}`}>{formatChange(fundDetail.nav_change)}</div>
                  <div className="text-gray-500 text-xs mt-1">日涨跌</div>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <div className="text-xl font-bold">{typeof fundDetail.acc_nav === "number" ? fundDetail.acc_nav.toFixed(4) : "-"}</div>
                  <div className="text-gray-500 text-xs mt-1">累计净值</div>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <div className={`text-xl font-bold ${changeColor(fundDetail.return_1y)}`}>{formatChange(fundDetail.return_1y)}</div>
                  <div className="text-gray-500 text-xs mt-1">近1年收益</div>
                </div>
              </div>
            </div>

            {/* 收益表现 */}
            <div className="p-6 border-b">
              <h3 className="font-medium mb-3">收益表现</h3>
              <div className="grid grid-cols-7 gap-2 text-center">
                {[
                  { label: "近1周", value: fundDetail.returns?.week_1 ?? fundDetail.return_1w },
                  { label: "近1月", value: fundDetail.returns?.month_1 ?? fundDetail.return_1m },
                  { label: "近3月", value: fundDetail.returns?.month_3 ?? fundDetail.return_3m },
                  { label: "近6月", value: fundDetail.returns?.month_6 ?? fundDetail.return_6m },
                  { label: "近1年", value: fundDetail.returns?.year_1 ?? fundDetail.return_1y },
                  { label: "近3年", value: fundDetail.returns?.year_3 ?? fundDetail.return_3y },
                  { label: "成立以来", value: fundDetail.returns?.since_establish },
                ].map((item) => (
                  <div key={item.label} className="p-2 bg-gray-50 rounded">
                    <div className={`text-sm font-bold font-mono ${changeColor(item.value)}`}>{formatChange(item.value)}</div>
                    <div className="text-xs text-gray-400 mt-1">{item.label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* 基金信息 */}
            <div className="p-6">
              <h3 className="font-medium mb-3">基金信息</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">基金类型</span>
                  <span>{fundDetail.fund_type || "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">成立日期</span>
                  <span>{fundDetail.establish_date || "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">基金规模</span>
                  <span>{typeof fundDetail.fund_scale === "number" ? `${(fundDetail.fund_scale / 1e8).toFixed(2)}亿` : "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">基金经理</span>
                  <span>{fundDetail.manager || "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">管理费率</span>
                  <span>{typeof fundDetail.management_fee === "number" ? `${fundDetail.management_fee}%` : "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">托管费率</span>
                  <span>{typeof fundDetail.custody_fee === "number" ? `${fundDetail.custody_fee}%` : "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">基金公司</span>
                  <span>{fundDetail.fund_company || "-"}</span>
                </div>
                <div className="flex justify-between py-2 border-b">
                  <span className="text-gray-500">托管银行</span>
                  <span>{fundDetail.custodian_bank || "-"}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!removeFundConfirm}
        title="确认移除该基金？"
        description={
          removeFundConfirm
            ? `${removeFundConfirm.name ? `${removeFundConfirm.name}（${removeFundConfirm.code}）` : removeFundConfirm.code} 将从关注列表移除。`
            : undefined
        }
        confirmText="移除"
        cancelText="取消"
        variant="danger"
        onCancel={() => setRemoveFundConfirm(null)}
        onConfirm={() => {
          const code = removeFundConfirm?.code;
          const name = removeFundConfirm?.name;
          setRemoveFundConfirm(null);
          if (!code) return;
          handleRemove(code, name);
        }}
      />
    </div>
  );
}
