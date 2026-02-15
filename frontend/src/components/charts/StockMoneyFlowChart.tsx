"use client";

import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import api from "@/lib/api";

interface MoneyFlowDay {
  date: string;
  main_net_inflow: number;
  main_net_inflow_pct?: number;
  close?: number;
  change_percent?: number;
  super_large_net_inflow?: number;
  large_net_inflow?: number;
  mid_net_inflow?: number;
  small_net_inflow?: number;
}

function toNumber(v: unknown, fallback = 0) {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function toYi(v: number) {
  if (!Number.isFinite(v)) return 0;
  return v / 1e8;
}
function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}


export default function StockMoneyFlowChart({ code, days = 60, height = 360 }: { code: string; days?: number; height?: number }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rows, setRows] = useState<MoneyFlowDay[]>([]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await api.getStockMoneyFlowHistory(code, days);
        if (cancelled) return;
        setRows(Array.isArray(data) ? data : []);
      } catch (errorObject: unknown) {
        if (cancelled) return;
        setRows([]);
        setError(getErrorMessage(errorObject, "加载资金流向失败"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [code, days]);

  const option = useMemo<EChartsOption | null>(() => {
    if (!rows.length) return null;

    const ordered = rows
      .filter((x) => x && x.date)
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));

    const dates = ordered.map((x) => x.date);
    const inflowYi = ordered.map((x) => toYi(toNumber(x.main_net_inflow)));
    const closes = ordered.map((x) => toNumber(x.close, NaN));

    return {
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: "#e5e7eb",
        borderWidth: 1,
        textStyle: { color: "#0f172a", fontSize: 12 },
        formatter: (params: unknown) => {
          const firstParam = Array.isArray(params) ? params[0] : params;
          const idx =
            firstParam && typeof firstParam === "object" && "dataIndex" in firstParam
              ? Number((firstParam as { dataIndex?: unknown }).dataIndex)
              : -1;
          if (!Number.isInteger(idx) || idx < 0 || idx >= ordered.length) return "";
          const item = ordered[idx];
          const inflow = inflowYi[idx];
          const close = closes[idx];
          return `
            <div style="padding:8px 10px;">
              <div style="font-weight:600;margin-bottom:6px;">${item.date}</div>
              <div>主力净流入：<span style="font-family:ui-monospace">${inflow >= 0 ? "+" : ""}${inflow.toFixed(2)}亿</span></div>
              <div>收盘价：<span style="font-family:ui-monospace">${Number.isFinite(close) ? close.toFixed(2) : "-"}</span></div>
              ${typeof item.main_net_inflow_pct === "number" ? `<div>主力净占比：<span style="font-family:ui-monospace">${item.main_net_inflow_pct.toFixed(2)}%</span></div>` : ""}
            </div>
          `;
        },
      },
      legend: {
        data: ["主力净流入(亿)", "收盘价"],
        top: 0,
        left: "center",
        textStyle: { fontSize: 11 },
        itemWidth: 14,
        itemHeight: 10,
      },
      grid: { left: 52, right: 40, top: 34, bottom: 44 },
      xAxis: {
        type: "category",
        data: dates,
        axisLabel: { fontSize: 10, color: "#64748b", formatter: (v: string) => String(v).slice(5) },
        axisLine: { lineStyle: { color: "#e5e7eb" } },
        axisTick: { show: false },
      },
      yAxis: [
        {
          type: "value",
          axisLabel: { fontSize: 10, color: "#64748b", formatter: (v: number) => `${v.toFixed(1)}亿` },
          splitLine: { lineStyle: { color: "#f1f5f9" } },
        },
        {
          type: "value",
          axisLabel: { fontSize: 10, color: "#64748b", formatter: (v: number) => v.toFixed(2) },
          splitLine: { show: false },
        },
      ],
      dataZoom: [
        { type: "inside", start: Math.max(0, 100 - Math.min(100, (45 / dates.length) * 100)), end: 100 },
        { type: "slider", height: 18, bottom: 8, start: Math.max(0, 100 - Math.min(100, (45 / dates.length) * 100)), end: 100 },
      ],
      series: [
        {
          name: "主力净流入(亿)",
          type: "bar",
          data: inflowYi.map((v) => ({
            value: v,
            itemStyle: { color: v >= 0 ? "#ef4444" : "#22c55e" },
          })),
          barWidth: "55%",
        },
        {
          name: "收盘价",
          type: "line",
          yAxisIndex: 1,
          data: closes,
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { width: 2, color: "#8b5cf6" },
          itemStyle: { color: "#8b5cf6" },
        },
      ],
    };
  }, [rows]);

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium">资金流向（主力净流入）</h3>
        <div className="text-xs text-gray-400 font-mono">{code}</div>
      </div>

      {loading && (
        <div className="flex items-center justify-center text-gray-400" style={{ height }}>
          加载资金流向...
        </div>
      )}
      {!loading && error && (
        <div className="flex items-center justify-center text-red-600" style={{ height }}>
          {error}
        </div>
      )}
      {!loading && !error && !option && (
        <div className="flex items-center justify-center text-gray-400" style={{ height }}>
          暂无资金流向数据
        </div>
      )}
      {!loading && !error && option && (
        <ReactECharts option={option} style={{ height }} notMerge={true} lazyUpdate={true} />
      )}
      <div className="text-xs text-gray-400 mt-2">注：净流入以“元”口径换算为“亿元”展示。</div>
    </div>
  );
}

