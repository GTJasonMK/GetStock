"use client";

import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import api from "@/lib/api";

interface ChipDistribution {
  date?: string;
  profit_ratio: number; // 0-1
  avg_cost: number;
  cost_90_low: number;
  cost_90_high: number;
  concentration_90: number; // 0-1
  cost_70_low: number;
  cost_70_high: number;
  concentration_70: number; // 0-1
  source?: string;
}

interface ChipDistributionResponse {
  stock_code: string;
  stock_name?: string;
  available: boolean;
  reason?: string;
  data?: ChipDistribution | null;
}

function clamp(v: number, min: number, max: number) {
  if (!Number.isFinite(v)) return min;
  return Math.min(max, Math.max(min, v));
}

function formatPct01(v: number) {
  const x = clamp(v, 0, 1) * 100;
  return `${x.toFixed(1)}%`;
}

export default function ChipDistributionChart({ code }: { code: string }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<ChipDistributionResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await api.getChipDistribution(code);
        if (cancelled) return;
        setPayload(data || null);
      } catch (e: any) {
        if (cancelled) return;
        setPayload(null);
        setError(e?.message || "加载筹码分布失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [code]);

  const gaugeOption = useMemo<EChartsOption | null>(() => {
    const d = payload?.data;
    if (!payload?.available || !d) return null;
    const profit = clamp(d.profit_ratio, 0, 1) * 100;
    return {
      series: [
        {
          type: "gauge",
          startAngle: 180,
          endAngle: 0,
          center: ["50%", "60%"],
          radius: "95%",
          min: 0,
          max: 100,
          splitNumber: 5,
          axisLine: {
            lineStyle: {
              width: 12,
              color: [
                [0.3, "#22c55e"],
                [0.7, "#f59e0b"],
                [1, "#ef4444"],
              ],
            },
          },
          pointer: { show: true, width: 4, length: "60%" },
          axisTick: { distance: -14, length: 4, lineStyle: { color: "#94a3b8" } },
          splitLine: { distance: -14, length: 10, lineStyle: { color: "#94a3b8" } },
          axisLabel: { distance: 4, color: "#64748b", fontSize: 10 },
          title: { show: true, offsetCenter: [0, "-10%"], fontSize: 12, color: "#0f172a" },
          detail: { valueAnimation: false, offsetCenter: [0, "35%"], fontSize: 20, fontFamily: "ui-monospace", color: "#0f172a", formatter: "{value}%" },
          data: [{ value: Number(profit.toFixed(1)), name: "获利盘比例" }],
        },
      ],
    };
  }, [payload]);

  const rangeOption = useMemo<EChartsOption | null>(() => {
    const d = payload?.data;
    if (!payload?.available || !d) return null;

    const low90 = d.cost_90_low;
    const high90 = d.cost_90_high;
    const low70 = d.cost_70_low;
    const high70 = d.cost_70_high;
    const avg = d.avg_cost;

    const xMin = Math.min(low90, low70, avg) * 0.97;
    const xMax = Math.max(high90, high70, avg) * 1.03;

    const categories = ["90%筹码区间", "70%筹码区间"];
    const invisible = [low90, low70];
    const ranges = [Math.max(0, high90 - low90), Math.max(0, high70 - low70)];

    return {
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: "#e5e7eb",
        borderWidth: 1,
        textStyle: { color: "#0f172a", fontSize: 12 },
        formatter: () => {
          return `
            <div style="padding:8px 10px;">
              <div style="font-weight:600;margin-bottom:6px;">筹码成本区间</div>
              <div>90%区间：<span style="font-family:ui-monospace">${low90.toFixed(2)} ~ ${high90.toFixed(2)}</span></div>
              <div>70%区间：<span style="font-family:ui-monospace">${low70.toFixed(2)} ~ ${high70.toFixed(2)}</span></div>
              <div>平均成本：<span style="font-family:ui-monospace">${avg.toFixed(2)}</span></div>
            </div>
          `;
        },
      },
      grid: { left: 86, right: 18, top: 10, bottom: 10 },
      xAxis: {
        type: "value",
        min: Number.isFinite(xMin) ? xMin : undefined,
        max: Number.isFinite(xMax) ? xMax : undefined,
        axisLabel: { fontSize: 10, color: "#64748b", formatter: (v: number) => v.toFixed(2) },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
      },
      yAxis: {
        type: "category",
        data: categories,
        axisLabel: { fontSize: 11, color: "#475569" },
        axisTick: { show: false },
        axisLine: { show: false },
      },
      series: [
        {
          name: "offset",
          type: "bar",
          stack: "cost",
          silent: true,
          itemStyle: { color: "transparent" },
          data: invisible,
        },
        {
          name: "range",
          type: "bar",
          stack: "cost",
          barWidth: 18,
          itemStyle: {
            color: "#93c5fd",
            borderColor: "#60a5fa",
            borderWidth: 1,
          },
          data: ranges,
          markLine: {
            symbol: ["none", "none"],
            lineStyle: { color: "#ef4444", width: 2, type: "solid" },
            label: { show: true, formatter: `平均成本 ${avg.toFixed(2)}`, color: "#ef4444" },
            data: [{ xAxis: avg }],
          },
        },
      ],
    };
  }, [payload]);

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium">筹码分布</h3>
        <div className="text-xs text-gray-400 font-mono">{code}</div>
      </div>

      {loading && <div className="text-center py-10 text-gray-400">加载筹码分布...</div>}
      {!loading && error && <div className="text-center py-10 text-red-600">{error}</div>}

      {!loading && !error && payload && !payload.available && (
        <div className="text-center py-10 text-gray-400">
          <div className="font-medium text-gray-600 mb-2">筹码分布不可用</div>
          <div className="text-sm">{payload.reason || "暂无数据"}</div>
        </div>
      )}

      {!loading && !error && payload?.available && payload.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-gray-50 rounded-xl">
              <div className="text-xs text-gray-500 mb-1">数据日期</div>
              <div className="font-mono">{payload.data.date || "-"}</div>
              <div className="text-xs text-gray-500 mt-3 mb-1">数据来源</div>
              <div className="font-mono">{payload.data.source || "-"}</div>
            </div>
            <div className="p-4 bg-gray-50 rounded-xl">
              <div className="text-xs text-gray-500 mb-1">平均成本</div>
              <div className="text-2xl font-bold font-mono">{payload.data.avg_cost?.toFixed(2) || "-"}</div>
              <div className="text-xs text-gray-500 mt-3 mb-1">获利盘比例</div>
              <div className="font-mono">{formatPct01(payload.data.profit_ratio)}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-white border rounded-xl p-3">
              {gaugeOption ? <ReactECharts option={gaugeOption} style={{ height: 240 }} notMerge={true} lazyUpdate={true} /> : null}
            </div>
            <div className="bg-white border rounded-xl p-3">
              {rangeOption ? <ReactECharts option={rangeOption} style={{ height: 240 }} notMerge={true} lazyUpdate={true} /> : null}
              <div className="mt-2 text-xs text-gray-400">
                90%集中度：{formatPct01(payload.data.concentration_90)}；70%集中度：{formatPct01(payload.data.concentration_70)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

