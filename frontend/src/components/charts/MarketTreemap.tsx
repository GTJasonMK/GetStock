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

type TreemapLeafNode = {
  name: string;
  value: number;
  stock_code: string;
  stock_name: string;
  industry: string;
  change_percent: number;
  amount: number | null;
  total_market_cap: number | null;
  itemStyle: {
    color: string;
    borderColor: string;
    borderWidth: number;
    gapWidth: number;
  };
  label: {
    show: boolean;
    color: string;
    fontSize: number;
    overflow: "truncate";
    formatter: (params: unknown) => string;
  };
};

type IndustryNode = {
  name: string;
  children: TreemapLeafNode[];
};

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
  if (typeof v !== "number" || !Number.isFinite(v)) return "#e5e7eb";
  if (v >= 7) return "#991b1b";
  if (v >= 3) return "#ef4444";
  if (v > 0) return "#fca5a5";
  if (v <= -7) return "#166534";
  if (v <= -3) return "#22c55e";
  if (v < 0) return "#86efac";
  return "#e5e7eb";
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const toFiniteNumber = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

const getNodeData = (params: unknown): Record<string, unknown> => {
  const first = Array.isArray(params) ? params[0] : params;
  if (!isRecord(first) || !isRecord(first.data)) return {};
  return first.data;
};

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
  for (const row of rows) {
    const key = String(row.industry || "").trim() || "其他";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(row);
  }

  const maxPerGroup = 25;
  const toSize = (item: MarketTreemapItem) => {
    const raw = sizeBy === "amount" ? item.amount : item.total_market_cap;
    return typeof raw === "number" && Number.isFinite(raw) ? Math.abs(raw) : 0;
  };

  const seriesData: IndustryNode[] = Array.from(grouped.entries())
    .map(([industry, list]) => {
      const children: TreemapLeafNode[] = [...list]
        .sort((a, b) => toSize(b) - toSize(a))
        .slice(0, maxPerGroup)
        .map((stock) => {
          const size = Math.max(1, toSize(stock));
          const change = typeof stock.change_percent === "number" ? stock.change_percent : 0;
          return {
            name: stock.stock_name || stock.stock_code,
            value: size,
            stock_code: stock.stock_code,
            stock_name: stock.stock_name,
            industry,
            change_percent: change,
            amount: typeof stock.amount === "number" ? stock.amount : null,
            total_market_cap: typeof stock.total_market_cap === "number" ? stock.total_market_cap : null,
            itemStyle: {
              color: colorByChange(change),
              borderColor: "#ffffff",
              borderWidth: 1,
              gapWidth: 1,
            },
            label: {
              show: true,
              color: "#0f172a",
              fontSize: 11,
              overflow: "truncate",
              formatter: (params: unknown) => {
                const node = getNodeData(params);
                const name = typeof node.name === "string" ? node.name : "";
                const pct = toFiniteNumber(node.change_percent);
                return `${name}\n${formatChange(pct)}`;
              },
            },
          };
        });

      return { name: industry, children };
    })
    .filter((node) => node.children.length > 0)
    .sort((a, b) => b.children.length - a.children.length);

  const option: EChartsOption = {
    tooltip: {
      borderWidth: 1,
      borderColor: "#e5e7eb",
      backgroundColor: "rgba(255,255,255,0.95)",
      textStyle: { color: "#0f172a", fontSize: 12 },
      formatter: (info: unknown) => {
        const d = getNodeData(info);
        const name = typeof d.stock_name === "string" ? d.stock_name : typeof d.name === "string" ? d.name : "";
        const code = typeof d.stock_code === "string" ? d.stock_code : "";
        const industry = typeof d.industry === "string" ? d.industry : "";
        const change = toFiniteNumber(d.change_percent);
        const amount = toFiniteNumber(d.amount);
        const marketCap = toFiniteNumber(d.total_market_cap);
        const lines = [
          `<div style="font-weight:600;margin-bottom:6px;">${name}${code ? `（${code}）` : ""}</div>`,
          industry ? `<div>行业：${industry}</div>` : "",
          `<div>涨跌幅：<span style="font-family:ui-monospace">${formatChange(change)}</span></div>`,
          `<div>成交额：<span style="font-family:ui-monospace">${formatMoneyYuan(amount)}</span></div>`,
          `<div>总市值：<span style="font-family:ui-monospace">${formatMoneyYuan(marketCap)}</span></div>`,
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
        data: seriesData,
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
