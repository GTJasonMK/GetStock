"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";

// 面板组件
import StocksPanel from "@/components/panels/StocksPanel";
import FundsPanel from "@/components/panels/FundsPanel";
import MarketPanel from "@/components/panels/MarketPanel";
import TechnicalPanel from "@/components/panels/TechnicalPanel";
import NewsPanel from "@/components/panels/NewsPanel";
import AIPanel from "@/components/panels/AIPanel";
import SettingsPanel from "@/components/panels/SettingsPanel";

// ============ 类型定义 ============
type TabKey = "stocks" | "funds" | "market" | "technical" | "news" | "ai" | "settings";

// ============ 主应用 ============
export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("stocks");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState(false);
  const [version, setVersion] = useState("");
  // 已访问过的 Tab 采用“挂载后保活”，避免切换回来重新拉取/重置状态导致体验卡顿
  const [mountedTabs, setMountedTabs] = useState<Record<TabKey, boolean>>({
    stocks: true,
    funds: false,
    market: false,
    technical: false,
    news: false,
    ai: false,
    settings: false,
  });

  useEffect(() => {
    checkBackend();
  }, []);

  useEffect(() => {
    setMountedTabs((prev) => (prev[activeTab] ? prev : { ...prev, [activeTab]: true }));
  }, [activeTab]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileNavOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileNavOpen]);

  const checkBackend = async () => {
    try {
      const data = await api.getVersion();
      setBackendOnline(true);
      setVersion(data.version || "");
    } catch {
      setBackendOnline(false);
    }
  };

  const tabs = useMemo(
    () => [
      { key: "stocks" as const, icon: "chart", label: "自选股" },
      { key: "funds" as const, icon: "fund", label: "基金" },
      { key: "market" as const, icon: "market", label: "市场数据" },
      { key: "technical" as const, icon: "analysis", label: "技术分析" },
      { key: "news" as const, icon: "news", label: "资讯搜索" },
      { key: "ai" as const, icon: "ai", label: "AI 助手" },
      { key: "settings" as const, icon: "settings", label: "系统设置" },
    ],
    []
  );

  const activeLabel = useMemo(() => tabs.find((t) => t.key === activeTab)?.label || "Stock Recon", [activeTab, tabs]);

  // 轻量预获取：鼠标 hover/键盘 focus 到导航项时提前拉取数据，减少进入页面的等待（平衡预取/缓存/持久化）
  const prefetchedRef = useRef<Set<TabKey>>(new Set());
  const prefetchTab = (key: TabKey) => {
    if (prefetchedRef.current.has(key)) return;
    prefetchedRef.current.add(key);

    const safe = (p: Promise<any>) => p.catch(() => {});
    if (key === "stocks") {
      safe(api.getGroups());
      safe(api.getFollowedStocks());
    } else if (key === "market") {
      safe(api.getMarketOverview());
      safe(api.getIndustryRank());
      safe(api.getConceptRank());
      safe(api.getNorthFlow(30));
      safe(api.getStockRank("change_percent", "desc", 50));
    } else if (key === "news") {
      safe(api.getLatestNews(undefined, 30));
      safe(api.getTelegraph(1, 30));
      safe(api.getGlobalIndexes());
    } else if (key === "settings") {
      safe(api.getSettings());
      safe(api.getDataSourceConfigs());
      safe(api.getAIConfigs());
      safe(api.getSearchEngines());
    }
  };

  return (
    <div className="flex h-[100dvh] bg-[var(--bg-primary)]">
      {/* 移动端顶部栏 */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-40 h-14 bg-white border-b border-[color:var(--border-color)] flex items-center justify-between px-4">
        <button
          type="button"
          onClick={() => setMobileNavOpen(true)}
          className="icon-btn"
          aria-label="打开导航菜单"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div className="min-w-0 flex-1 px-3">
          <div className="truncate text-sm font-semibold text-[var(--text-primary)]">{activeLabel}</div>
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className={`w-2 h-2 rounded-full ${backendOnline ? "bg-emerald-500" : "bg-red-500"}`} aria-hidden="true" />
            <span>{backendOnline ? `后端在线${version ? ` v${version}` : ""}` : "后端离线"}</span>
          </div>
        </div>

        <button
          type="button"
          onClick={checkBackend}
          className="icon-btn"
          aria-label="刷新后端状态"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.5 12a7.5 7.5 0 0113.309-4.86M19.5 12a7.5 7.5 0 01-13.309 4.86M19.5 7.14V4.5h-2.64M4.5 16.86V19.5h2.64" />
          </svg>
        </button>
      </header>

      {/* 桌面端左侧边栏 */}
      <aside className="hidden lg:flex w-[var(--sidebar-width)] bg-[var(--bg-sidebar)] text-[var(--text-sidebar)] flex-col">
        <div className="h-14 flex items-center px-5 border-b border-[color:var(--bg-sidebar-hover)]">
          <span className="text-white font-semibold text-base">Stock Recon</span>
        </div>

        <nav className="flex-1 py-3">
          {tabs.map((t) => (
            <NavItem
              key={t.key}
              icon={t.icon}
              label={t.label}
              active={activeTab === t.key}
              onClick={() => setActiveTab(t.key)}
              onPrefetch={() => prefetchTab(t.key)}
            />
          ))}
        </nav>

        <div className="p-4 border-t border-[color:var(--bg-sidebar-hover)]">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className={`w-2 h-2 rounded-full ${backendOnline ? "bg-emerald-500" : "bg-red-500"}`} aria-hidden="true" />
              <span className="text-xs text-[var(--text-sidebar)] truncate">
                {backendOnline ? `后端在线${version ? ` v${version}` : ""}` : "后端离线"}
              </span>
            </div>
            <button type="button" onClick={checkBackend} className="icon-btn text-[var(--text-sidebar)]" aria-label="刷新后端状态">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.5 12a7.5 7.5 0 0113.309-4.86M19.5 12a7.5 7.5 0 01-13.309 4.86M19.5 7.14V4.5h-2.64M4.5 16.86V19.5h2.64" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* 移动端抽屉导航 */}
      {mobileNavOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <button
            type="button"
            className="absolute inset-0 bg-black/40 cursor-pointer"
            aria-label="关闭导航菜单"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="absolute left-0 top-0 bottom-0 w-[280px] bg-[var(--bg-sidebar)] text-[var(--text-sidebar)] flex flex-col">
            <div className="h-14 flex items-center justify-between px-5 border-b border-[color:var(--bg-sidebar-hover)]">
              <span className="text-white font-semibold text-base">Stock Recon</span>
              <button type="button" className="icon-btn text-[var(--text-sidebar)]" onClick={() => setMobileNavOpen(false)} aria-label="关闭">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <nav className="flex-1 py-3">
              {tabs.map((t) => (
                <NavItem
                  key={t.key}
                  icon={t.icon}
                  label={t.label}
                  active={activeTab === t.key}
                  onClick={() => {
                    setActiveTab(t.key);
                    setMobileNavOpen(false);
                  }}
                  onPrefetch={() => prefetchTab(t.key)}
                />
              ))}
            </nav>
          </aside>
        </div>
      )}

      {/* 主内容区 */}
      <main className="flex-1 overflow-auto bg-[var(--bg-primary)] lg:pt-0 pt-14">
        {mountedTabs.stocks && (
          <section hidden={activeTab !== "stocks"} aria-hidden={activeTab !== "stocks"} className="h-full">
            <StocksPanel active={activeTab === "stocks"} />
          </section>
        )}
        {mountedTabs.funds && (
          <section hidden={activeTab !== "funds"} aria-hidden={activeTab !== "funds"} className="h-full">
            <FundsPanel />
          </section>
        )}
        {mountedTabs.market && (
          <section hidden={activeTab !== "market"} aria-hidden={activeTab !== "market"} className="h-full">
            <MarketPanel />
          </section>
        )}
        {mountedTabs.technical && (
          <section hidden={activeTab !== "technical"} aria-hidden={activeTab !== "technical"} className="h-full">
            <TechnicalPanel />
          </section>
        )}
        {mountedTabs.news && (
          <section hidden={activeTab !== "news"} aria-hidden={activeTab !== "news"} className="h-full">
            <NewsPanel />
          </section>
        )}
        {mountedTabs.ai && (
          <section hidden={activeTab !== "ai"} aria-hidden={activeTab !== "ai"} className="h-full">
            <AIPanel />
          </section>
        )}
        {mountedTabs.settings && (
          <section hidden={activeTab !== "settings"} aria-hidden={activeTab !== "settings"} className="h-full">
            <SettingsPanel />
          </section>
        )}
      </main>
    </div>
  );
}

// ============ 导航项组件 ============
function NavItem({
  icon,
  label,
  active,
  onClick,
  onPrefetch,
}: {
  icon: string;
  label: string;
  active: boolean;
  onClick: () => void;
  onPrefetch?: () => void;
}) {
  const icons: Record<string, string> = {
    chart: "M3 3v18h18M9 17V9m4 8v-5m4 5V6",
    fund: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    market: "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",
    analysis: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6m14 0v-3a2 2 0 00-2-2h-2a2 2 0 00-2 2v3m14 0H3m8-14v3m-4-3v3m8-3v3",
    news: "M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9.5a2 2 0 00-2-2h-2",
    ai: "M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z",
    settings: "M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93s.844.082 1.168-.205l.645-.645a1.183 1.183 0 011.673 0l.773.773c.463.463.463 1.21 0 1.673l-.645.645c-.287.324-.37.772-.205 1.168s.506.71.93.78l.894.15c.542.09.94.56.94 1.109v1.094c0 .55-.398 1.02-.94 1.11l-.894.149c-.424.07-.764.384-.93.78s-.082.844.205 1.168l.645.645c.463.463.463 1.21 0 1.673l-.773.773a1.183 1.183 0 01-1.673 0l-.645-.645c-.324-.287-.772-.37-1.168-.205s-.71.506-.78.93l-.15.894c-.09.542-.56.94-1.109.94h-1.094c-.55 0-1.02-.398-1.11-.94l-.149-.894c-.07-.424-.384-.764-.78-.93s-.844-.082-1.168.205l-.645.645a1.183 1.183 0 01-1.673 0l-.773-.773a1.183 1.183 0 010-1.673l.645-.645c.287-.324.37-.772.205-1.168s-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.764-.384.93-.78s.082-.844-.205-1.168l-.645-.645a1.183 1.183 0 010-1.673l.773-.773a1.183 1.183 0 011.673 0l.645.645c.324.287.772.37 1.168.205s.71-.506.78-.93l.15-.894z",
  };

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={onPrefetch}
      onFocus={onPrefetch}
      aria-current={active ? "page" : undefined}
      className={`w-full flex items-center gap-3 px-5 py-3 text-sm transition-colors duration-200 cursor-pointer ${
        active
          ? "bg-[var(--bg-sidebar-active)] text-[var(--text-sidebar-active)]"
          : "text-[var(--text-sidebar)] hover:bg-[var(--bg-sidebar-hover)] hover:text-[var(--text-sidebar-active)]"
      }`}
    >
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={icons[icon]} />
      </svg>
      {label}
    </button>
  );
}
