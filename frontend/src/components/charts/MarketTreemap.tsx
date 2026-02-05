"use client";

import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";

export interface MarketTreemapItem {
  stock_code: string;
  stock_name: string;
  change_percent?: number;
  amount?: number;
  total_market_cap?: number;
  industry?: string;
}

function formatChange(v: number | null | undefined) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function formatMoneyYuan(v: number | null | undefined) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "-";
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(2)}万`;
  return v.toFixed(2);
}

function colorByChange(v: number | null | undefined) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "#e5e7eb"; // gray-200
  if (v >= 7) return "#991b1b"; // red-800
  if (v >= 3) return "#ef4444"; // red-500
  if (v > 0) return "#fca5a5"; // red-300
  if (v <= -7) return "#166534"; // green-800
  if (v <= -3) return "#22c55e"; // green-500
  if (v < 0) return "#86efac"; // green-300
  return "#e5e7eb";
}

export default function MarketTreemap({
  title,
  items,
  height = 560,
  sizeBy = "total_market_cap",
}: {
  title: string;
  items: MarketTreemapItem[];
  height?: number;
  sizeBy?: "total_market_cap" | "amount";
}) {
  const rows = (items || []).filter((x) => x && String(x.stock_code || "").trim());

  const grouped = new Map<string, MarketTreemapItem[]>();
  for (const r of rows) {
    const key = String(r.industry || "").trim() || "其他";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(r);
  }

  // 行业内按 sizeBy 取前 N，避免 treemap 过密导致可读性差
  const MAX_PER_GROUP = 25;
  const toSize = (r: MarketTreemapItem) => {
    const raw = sizeBy === "amount" ? r.amount : r.total_market_cap;
    return typeof raw === "number" && Number.isFinite(raw) ? Math.abs(raw) : 0;
  };

  const seriesData = Array.from(grouped.entries())
    .map(([industry, list]) => {
      const children = [...list]
        .sort((a, b) => toSize(b) - toSize(a))
        .slice(0, MAX_PER_GROUP)
        .map((s) => {
          const size = Math.max(1, toSize(s));
          const chg = typeof s.change_percent === "number" ? s.change_percent : 0;
          return {
            name: s.stock_name || s.stock_code,
            value: size,
            stock_code: s.stock_code,
            stock_name: s.stock_name,
            industry,
            change_percent: chg,
            amount: typeof s.amount === "number" ? s.amount : null,
            total_market_cap: typeof s.total_market_cap === "number" ? s.total_market_cap : null,
            itemStyle: {
              color: colorByChange(chg),
              borderColor: "#ffffff",
              borderWidth: 1,
              gapWidth: 1,
            },
            label: {
              show: true,
              color: "#0f172a",
              fontSize: 11,
              overflow: "truncate" as const,
              formatter: (p: any) => {
                const nm = p?.name || "";
                const pct = p?.data?.change_percent;
                return `${nm}\n${formatChange(pct)}`;
              },
            },
          };
        });

      return {
        name: industry,
        children,
      };
    })
    .filter((x) => (x.children || []).length > 0)
    .sort((a: any, b: any) => (b.children?.length || 0) - (a.children?.length || 0));

  const option: EChartsOption = {
    tooltip: {
      borderWidth: 1,
      borderColor: "#e5e7eb",
      backgroundColor: "rgba(255,255,255,0.95)",
      textStyle: { color: "#0f172a", fontSize: 12 },
      formatter: (info: any) => {
        const d = info?.data || {};
        const name = String(d.stock_name || d.name || "");
        const code = String(d.stock_code || "");
        const industry = String(d.industry || "");
        const chg = d.change_percent as number | undefined;
        const amount = d.amount as number | undefined;
        const mc = d.total_market_cap as number | undefined;
        const lines = [
          `<div style="font-weight:600;margin-bottom:6px;">${name}${code ? `（${code}）` : ""}</div>`,
          industry ? `<div>行业：${industry}</div>` : "",
          `<div>涨跌幅：<span style="font-family:ui-monospace">${formatChange(chg)}</span></div>`,
          `<div>成交额：<span style="font-family:ui-monospace">${formatMoneyYuan(amount)}</span></div>`,
          `<div>总市值：<span style="font-family:ui-monospace">${formatMoneyYuan(mc)}</span></div>`,
        ].filter(Boolean);
        return `<div style="padding:8px 10px;">${lines.join("")}</div>`;
      },
    },
    title: {
      text: title,
      left: "center",
      top: 6,
      textStyle: { fontSize: 14, fontWeight: 600, color: "#0f172a" },
    },
    series: [
      {
        type: "treemap",
        top: 36,
        left: 10,
        right: 10,
        bottom: 10,
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        label: { show: true },
        upperLabel: {
          show: true,
          height: 22,
          color: "#0f172a",
          fontWeight: 600,
        },
        levels: [
          {
            itemStyle: { borderColor: "#ffffff", borderWidth: 2, gapWidth: 2 },
          },
          {
            itemStyle: { borderColor: "#ffffff", borderWidth: 1, gapWidth: 1 },
          },
        ],
        data: seriesData as any,
      },
    ],
  };

  if (rows.length === 0) {
    return <div className="text-center py-12 text-gray-400">暂无市场热力图数据</div>;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <ReactECharts option={option} style={{ height }} notMerge={true} lazyUpdate={true} />
      <div className="text-xs text-gray-400 mt-2">
        说明：面积≈{sizeBy === "amount" ? "成交额" : "总市值"}绝对值，颜色≈涨跌幅（红涨绿跌）；按行业分组展示。
      </div>
    </div>
  );
}

