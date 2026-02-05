"use client";

import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import api from "@/lib/api";

interface MinutePoint {
  time: string;
  price: number;
  volume: number;
  avg_price: number;
}

interface MinuteDataResponse {
  stock_code: string;
  stock_name: string;
  available?: boolean;
  reason?: string;
  source?: string;
  data: MinutePoint[];
}

function toNumber(v: unknown, fallback = 0) {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export default function StockMinuteChart({ code, height = 360 }: { code: string; height?: number }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState<MinuteDataResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await api.getMinuteData(code);
        if (cancelled) return;
        setPayload(data || null);
      } catch (e: any) {
        if (cancelled) return;
        setPayload(null);
        setError(e?.message || "加载分时数据失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [code]);

  const option = useMemo<EChartsOption | null>(() => {
    const rows = payload?.data || [];
    if (!rows.length) return null;

    const times = rows.map((x) => x.time);
    const prices = rows.map((x) => toNumber(x.price));
    const avgs = rows.map((x) => toNumber(x.avg_price));
    const volumes = rows.map((x) => toNumber(x.volume));

    const minPrice = Math.min(...prices.filter((x) => Number.isFinite(x)));
    const maxPrice = Math.max(...prices.filter((x) => Number.isFinite(x)));
    const pad = Math.max(0.01, (maxPrice - minPrice) * 0.05);

    const volumeBars = volumes.map((v, i) => {
      const prev = i > 0 ? prices[i - 1] : prices[i];
      const cur = prices[i];
      const up = cur >= prev;
      return {
        value: v,
        itemStyle: { color: up ? "#ef4444" : "#22c55e" },
      };
    });

    return {
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(255,255,255,0.95)",
        borderColor: "#e5e7eb",
        borderWidth: 1,
        textStyle: { color: "#0f172a", fontSize: 12 },
      },
      legend: {
        data: ["价格", "均价", "成交量"],
        top: 0,
        left: "center",
        textStyle: { fontSize: 11 },
        itemWidth: 14,
        itemHeight: 10,
      },
      grid: [
        { left: 52, right: 18, top: 34, height: "55%" },
        { left: 52, right: 18, top: "72%", height: "20%" },
      ],
      xAxis: [
        {
          type: "category",
          data: times,
          boundaryGap: false,
          axisLine: { lineStyle: { color: "#e5e7eb" } },
          axisLabel: { fontSize: 10, color: "#64748b" },
          splitLine: { show: false },
        },
        {
          type: "category",
          gridIndex: 1,
          data: times,
          boundaryGap: true,
          axisLine: { lineStyle: { color: "#e5e7eb" } },
          axisLabel: { fontSize: 10, color: "#64748b" },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          type: "value",
          scale: true,
          min: minPrice - pad,
          max: maxPrice + pad,
          axisLabel: { fontSize: 10, color: "#64748b", formatter: (v: number) => v.toFixed(2) },
          splitLine: { lineStyle: { color: "#f1f5f9" } },
        },
        {
          type: "value",
          gridIndex: 1,
          axisLabel: {
            fontSize: 10,
            color: "#64748b",
            formatter: (v: number) => (v >= 10000 ? `${(v / 10000).toFixed(0)}万` : String(Math.round(v))),
          },
          splitLine: { lineStyle: { color: "#f1f5f9" } },
        },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: "slider", xAxisIndex: [0, 1], height: 18, bottom: 8, start: 0, end: 100 },
      ],
      series: [
        {
          name: "价格",
          type: "line",
          data: prices,
          symbol: "none",
          lineStyle: { width: 2, color: "#3b82f6" },
        },
        {
          name: "均价",
          type: "line",
          data: avgs,
          symbol: "none",
          lineStyle: { width: 1.5, color: "#f59e0b" },
        },
        {
          name: "成交量",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeBars,
          barWidth: "60%",
        },
      ],
    };
  }, [payload]);

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium">分时图</h3>
        <div className="text-xs text-gray-400 font-mono">{code}</div>
      </div>

      {loading && (
        <div className="flex items-center justify-center text-gray-400" style={{ height }}>
          加载分时数据...
        </div>
      )}
      {!loading && error && (
        <div className="flex items-center justify-center text-red-600" style={{ height }}>
          {error}
        </div>
      )}
      {!loading && !error && !option && (
        <div className="flex items-center justify-center text-gray-400" style={{ height }}>
          {payload?.available === false
            ? (payload.reason || "分时数据暂不可用，请检查数据源配置或稍后重试")
            : "暂无分时数据"}
        </div>
      )}

      {!loading && !error && option && (
        <ReactECharts option={option} style={{ height }} notMerge={true} lazyUpdate={true} />
      )}
    </div>
  );
}
