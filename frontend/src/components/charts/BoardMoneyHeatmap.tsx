"use client";

import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";

export interface BoardMoneyItem {
  bk_code?: string;
  name: string;
  change_percent?: number;
  main_net_inflow?: number;
  main_net_inflow_percent?: number;
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
  if (typeof v !== "number" || !Number.isFinite(v)) return "#e5e7eb";
  if (v >= 5) return "#b91c1c";
  if (v >= 2) return "#ef4444";
  if (v > 0) return "#fca5a5";
  if (v <= -5) return "#15803d";
  if (v <= -2) return "#22c55e";
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

export default function BoardMoneyHeatmap({
  title,
  items,
  height = 520,
}: {
  title: string;
  items: BoardMoneyItem[];
  height?: number;
}) {
  const rows = (items || []).filter((x) => x && String(x.name || "").trim());

  const data = rows.map((x) => {
    const inflow = typeof x.main_net_inflow === "number" ? x.main_net_inflow : 0;
    const change = typeof x.change_percent === "number" ? x.change_percent : 0;
    const size = Math.max(1, Math.abs(inflow));
    return {
      name: x.name,
      value: size,
      bk_code: x.bk_code || "",
      change_percent: change,
      main_net_inflow: inflow,
      main_net_inflow_percent: typeof x.main_net_inflow_percent === "number" ? x.main_net_inflow_percent : null,
      itemStyle: {
        color: colorByChange(change),
        borderColor: "#ffffff",
        borderWidth: 2,
        gapWidth: 2,
      },
      label: {
        show: true,
        color: "#0f172a",
        fontSize: 12,
        overflow: "truncate" as const,
        formatter: (params: unknown) => {
          const node = getNodeData(params);
          const chg = toFiniteNumber(node.change_percent);
          const nm = typeof node.name === "string" ? node.name : "";
          return `${nm}\n${formatChange(chg)}`;
        },
      },
    };
  });

  const option: EChartsOption = {
    tooltip: {
      borderWidth: 1,
      borderColor: "#e5e7eb",
      backgroundColor: "rgba(255,255,255,0.95)",
      textStyle: { color: "#0f172a", fontSize: 12 },
      formatter: (info: unknown) => {
        const d = getNodeData(info);
        const name = typeof d.name === "string" ? d.name : "";
        const code = typeof d.bk_code === "string" ? d.bk_code : "";
        const chg = toFiniteNumber(d.change_percent);
        const inflow = toFiniteNumber(d.main_net_inflow);
        const pct = toFiniteNumber(d.main_net_inflow_percent);
        const lines = [
          `<div style="font-weight:600;margin-bottom:6px;">${name}${code ? `（${code}）` : ""}</div>`,
          `<div>涨跌幅：<span style="font-family:ui-monospace">${formatChange(chg)}</span></div>`,
          `<div>主力净流入：<span style="font-family:ui-monospace">${formatMoneyYuan(inflow)}</span></div>`,
        ];
        if (typeof pct === "number" && Number.isFinite(pct)) {
          lines.push(`<div>净流入占比：<span style="font-family:ui-monospace">${pct.toFixed(2)}%</span></div>`);
        }
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
        data,
      },
    ],
  };

  if (rows.length === 0) {
    return <div className="text-center py-12 text-gray-400">暂无热力图数据</div>;
  }

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <ReactECharts option={option} style={{ height }} notMerge={true} lazyUpdate={true} />
      <div className="text-xs text-gray-400 mt-2">
        说明：面积≈主力净流入绝对值，颜色≈涨跌幅（红涨绿跌）。
      </div>
    </div>
  );
}
