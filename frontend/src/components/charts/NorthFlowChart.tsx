"use client";

import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";

export interface NorthFlowHistoryItem {
  date: string;
  sh_inflow: number;
  sz_inflow: number;
  total_inflow: number;
}

function formatYi(v: number) {
  if (!Number.isFinite(v)) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}亿`;
}

function toYi(v: number, unit: string) {
  if (!Number.isFinite(v)) return 0;
  // 后端目前默认 unit=元；若未来返回“亿”，则直接使用
  if ((unit || "").includes("亿")) return v;
  return v / 1e8;
}

export default function NorthFlowChart({
  metric,
  unit,
  history,
  height = 360,
}: {
  metric?: string;
  unit?: string;
  history: NorthFlowHistoryItem[];
  height?: number;
}) {
  const safeUnit = unit || "元";
  const rows = (history || [])
    .filter((x) => x && x.date)
    .slice()
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));

  if (rows.length === 0) {
    return <div className="text-center py-10 text-gray-400">暂无走势数据</div>;
  }

  const dates = rows.map((x) => x.date);
  const sh = rows.map((x) => toYi(Number(x.sh_inflow || 0), safeUnit));
  const sz = rows.map((x) => toYi(Number(x.sz_inflow || 0), safeUnit));
  const total = rows.map((x) => toYi(Number(x.total_inflow || 0), safeUnit));

  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: "rgba(255,255,255,0.95)",
      borderColor: "#e5e7eb",
      borderWidth: 1,
      textStyle: { color: "#0f172a", fontSize: 12 },
      formatter: (params: any) => {
        const idx = params?.[0]?.dataIndex ?? -1;
        if (idx < 0 || idx >= rows.length) return "";
        const r = rows[idx];
        const label = metric || "净买额";
        return `
          <div style="padding:8px 10px;">
            <div style="font-weight:600;margin-bottom:6px;">${r.date}</div>
            <div>沪股通：<span style="font-family:ui-monospace">${formatYi(sh[idx])}</span></div>
            <div>深股通：<span style="font-family:ui-monospace">${formatYi(sz[idx])}</span></div>
            <div>合计：<span style="font-family:ui-monospace">${formatYi(total[idx])}</span></div>
            <div style="margin-top:6px;color:#64748b;">口径：${label}（亿元）</div>
          </div>
        `;
      },
    },
    legend: {
      data: ["沪股通", "深股通", "合计"],
      top: 0,
      left: "center",
      textStyle: { fontSize: 11 },
      itemWidth: 14,
      itemHeight: 10,
    },
    grid: { left: 50, right: 18, top: 34, bottom: 44 },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        fontSize: 10,
        formatter: (v: string) => (String(v).length >= 10 ? String(v).slice(5) : String(v)),
      },
      axisLine: { lineStyle: { color: "#e5e7eb" } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 10, formatter: (v: number) => `${v.toFixed(1)}亿` },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    dataZoom: [
      { type: "inside", start: Math.max(0, 100 - Math.min(100, (30 / rows.length) * 100)), end: 100 },
      { type: "slider", height: 18, bottom: 10, start: Math.max(0, 100 - Math.min(100, (30 / rows.length) * 100)), end: 100 },
    ],
    series: [
      {
        name: "沪股通",
        type: "bar",
        data: sh,
        barWidth: "35%",
        itemStyle: { color: (p: any) => (Number(p?.value) >= 0 ? "#ef4444" : "#22c55e") },
        emphasis: { focus: "series" },
        stack: "north",
      },
      {
        name: "深股通",
        type: "bar",
        data: sz,
        barWidth: "35%",
        itemStyle: { color: (p: any) => (Number(p?.value) >= 0 ? "#f97316" : "#16a34a") },
        emphasis: { focus: "series" },
        stack: "north",
      },
      {
        name: "合计",
        type: "line",
        data: total,
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { width: 2, color: "#8b5cf6" },
        itemStyle: { color: "#8b5cf6" },
      },
    ],
  };

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <ReactECharts option={option} style={{ height }} notMerge={true} lazyUpdate={true} />
      <div className="text-xs text-gray-400 mt-2">
        注：为便于对比，统一换算为亿元展示（原始单位：{unit || "元"}）。
      </div>
    </div>
  );
}

