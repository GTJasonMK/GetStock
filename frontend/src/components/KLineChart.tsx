"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import * as echarts from "echarts";
import api from "@/lib/api";

interface KLineChartProps {
  code: string;
  initialPeriod?: string;
  height?: number;
}

type IndicatorType = "volume" | "macd" | "rsi";
type AdjustType = "qfq" | "hfq" | "none";
type KLinePoint = {
  date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const toNumber = (value: unknown, fallback = 0): number => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
};

const normalizeKLinePoint = (value: unknown): KLinePoint | null => {
  if (!isRecord(value)) return null;
  const date = typeof value.date === "string" ? value.date : "";
  if (!date) return null;
  return {
    date,
    open: toNumber(value.open),
    close: toNumber(value.close),
    low: toNumber(value.low),
    high: toNumber(value.high),
    volume: toNumber(value.volume),
  };
};

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message) return error.message;
  if (isRecord(error) && typeof error.message === "string") return error.message;
  return fallback;
};

const isOverseaStockCode = (code: string): boolean => {
  const v = (code || "").trim().toLowerCase();
  return v.startsWith("hk") || v.startsWith("us");
};

export default function KLineChart({ code, initialPeriod = "day", height = 500 }: KLineChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [source, setSource] = useState("");
  const [period, setPeriod] = useState(initialPeriod);
  const [adjust, setAdjust] = useState<AdjustType>("qfq");
  const [indicator, setIndicator] = useState<IndicatorType>("volume");
  const [klineData, setKlineData] = useState<KLinePoint[]>([]);
  const oversea = isOverseaStockCode(code);

  // 港/美股：仅支持日/周/月K，避免用户点到 5min 等导致报错
  useEffect(() => {
    if (!oversea) return;
    if (["day", "week", "month"].includes(period)) return;
    setPeriod("day");
  }, [oversea, period]);

  // 计算EMA
  const calculateEMA = useCallback((data: number[], period: number): number[] => {
    const result: number[] = [];
    const k = 2 / (period + 1);
    let ema = data[0];
    result.push(ema);
    for (let i = 1; i < data.length; i++) {
      ema = data[i] * k + ema * (1 - k);
      result.push(ema);
    }
    return result;
  }, []);

  // 计算MACD
  const calculateMACD = useCallback((closes: number[]): { dif: number[]; dea: number[]; macd: number[] } => {
    const ema12 = calculateEMA(closes, 12);
    const ema26 = calculateEMA(closes, 26);
    const dif = ema12.map((v, i) => v - ema26[i]);
    const dea = calculateEMA(dif, 9);
    const macd = dif.map((v, i) => (v - dea[i]) * 2);
    return { dif, dea, macd };
  }, [calculateEMA]);

  // 计算RSI
  const calculateRSI = useCallback((closes: number[], period: number): number[] => {
    const result: number[] = [];
    for (let i = 0; i < closes.length; i++) {
      if (i < period) {
        result.push(50); // 数据不足时填充50
        continue;
      }
      let gains = 0;
      let losses = 0;
      for (let j = i - period + 1; j <= i; j++) {
        const change = closes[j] - closes[j - 1];
        if (change > 0) gains += change;
        else losses -= change;
      }
      const rs = losses === 0 ? 100 : gains / losses;
      result.push(100 - 100 / (1 + rs));
    }
    return result;
  }, []);

  // 计算MA均线
  const calculateMA = useCallback((data: KLinePoint[], dayCount: number): (number | string)[] => {
    const result: (number | string)[] = [];
    for (let i = 0; i < data.length; i++) {
      if (i < dayCount - 1) {
        result.push("-");
        continue;
      }
      let sum = 0;
      for (let j = 0; j < dayCount; j++) {
        sum += data[i - j].close;
      }
      result.push(Number((sum / dayCount).toFixed(2)));
    }
    return result;
  }, []);

  // 获取数据
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError("");
      setNotice("");
      try {
        const data = await api.getKlineData(code, period, 150, adjust);
        setSource(data?.source || "");
        if (data?.available === false) {
          setKlineData([]);
          setError(data?.reason || "K线数据暂不可用");
        } else {
          const list = Array.isArray(data?.data)
            ? data.data
                .map((item) => normalizeKLinePoint(item))
                .filter((item): item is KLinePoint => item !== null)
            : [];
          setKlineData(list);
          if (list.length === 0) setNotice("暂无K线数据");
        }
      } catch (errorObject: unknown) {
        setError(getErrorMessage(errorObject, "加载K线数据失败"));
        setKlineData([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [code, period, adjust]);

  // 渲染图表
  useEffect(() => {
    if (!chartRef.current || klineData.length === 0) return;

    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    const dates = klineData.map((item) => item.date);
    const ohlc = klineData.map((item) => [item.open, item.close, item.low, item.high]);
    const volumes = klineData.map((item) => item.volume);
    const closes = klineData.map((item) => item.close);

    // 计算指标
    const { dif, dea, macd } = calculateMACD(closes);
    const rsi6 = calculateRSI(closes, 6);
    const rsi12 = calculateRSI(closes, 12);
    const rsi24 = calculateRSI(closes, 24);

    // 基础grid布局
    const grids: echarts.GridComponentOption[] = [
      { left: "8%", right: "3%", top: "8%", height: "50%" },
      { left: "8%", right: "3%", top: "65%", height: "25%" },
    ];

    // 基础xAxis
    const xAxes: echarts.XAXisComponentOption[] = [
      {
        type: "category",
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: "#ddd" } },
        axisLabel: { fontSize: 10, formatter: (v: string) => v.substring(5) },
        splitLine: { show: false },
      },
      {
        type: "category",
        gridIndex: 1,
        data: dates,
        boundaryGap: true,
        axisLine: { lineStyle: { color: "#ddd" } },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ];

    // 基础yAxis
    const yAxes: echarts.YAXisComponentOption[] = [
      {
        scale: true,
        splitArea: { show: false },
        axisLine: { lineStyle: { color: "#ddd" } },
        splitLine: { lineStyle: { color: "#f0f0f0" } },
        axisLabel: { fontSize: 10, formatter: (v: number) => v.toFixed(2) },
      },
      {
        scale: true,
        gridIndex: 1,
        splitNumber: 2,
        axisLine: { lineStyle: { color: "#ddd" } },
        splitLine: { lineStyle: { color: "#f0f0f0" } },
        axisLabel: { fontSize: 10 },
      },
    ];

    // 基础series
    const series: echarts.SeriesOption[] = [
      {
        name: "K线",
        type: "candlestick",
        data: ohlc,
        itemStyle: {
          color: "#ef4444",
          color0: "#22c55e",
          borderColor: "#ef4444",
          borderColor0: "#22c55e",
        },
      },
      {
        name: "MA5",
        type: "line",
        data: calculateMA(klineData, 5),
        smooth: true,
        lineStyle: { width: 1, color: "#f59e0b" },
        symbol: "none",
      },
      {
        name: "MA10",
        type: "line",
        data: calculateMA(klineData, 10),
        smooth: true,
        lineStyle: { width: 1, color: "#3b82f6" },
        symbol: "none",
      },
      {
        name: "MA20",
        type: "line",
        data: calculateMA(klineData, 20),
        smooth: true,
        lineStyle: { width: 1, color: "#a855f7" },
        symbol: "none",
      },
    ];

    // 根据指标类型添加子图series
    if (indicator === "volume") {
      series.push({
        name: "成交量",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumes.map((v: number, i: number) => ({
          value: v,
          itemStyle: {
            color: klineData[i].close >= klineData[i].open ? "#ef4444" : "#22c55e",
          },
        })),
      });
      yAxes[1].axisLabel = {
        fontSize: 10,
        formatter: (v: number) => (v >= 10000 ? (v / 10000).toFixed(0) + "万" : v.toFixed(0)),
      };
    } else if (indicator === "macd") {
      series.push(
        {
          name: "DIF",
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: dif.map((v) => v.toFixed(3)),
          lineStyle: { width: 1, color: "#3b82f6" },
          symbol: "none",
        },
        {
          name: "DEA",
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: dea.map((v) => v.toFixed(3)),
          lineStyle: { width: 1, color: "#f59e0b" },
          symbol: "none",
        },
        {
          name: "MACD",
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: macd.map((v) => ({
            value: v.toFixed(3),
            itemStyle: { color: v >= 0 ? "#ef4444" : "#22c55e" },
          })),
        }
      );
    } else if (indicator === "rsi") {
      series.push(
        {
          name: "RSI6",
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: rsi6.map((v) => v.toFixed(2)),
          lineStyle: { width: 1, color: "#f59e0b" },
          symbol: "none",
        },
        {
          name: "RSI12",
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: rsi12.map((v) => v.toFixed(2)),
          lineStyle: { width: 1, color: "#3b82f6" },
          symbol: "none",
        },
        {
          name: "RSI24",
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: rsi24.map((v) => v.toFixed(2)),
          lineStyle: { width: 1, color: "#a855f7" },
          symbol: "none",
        }
      );
      // RSI参考线
      yAxes[1].min = 0;
      yAxes[1].max = 100;
      if ("splitNumber" in yAxes[1]) {
        yAxes[1].splitNumber = 4;
      }
    }

    // 图例
    const legendData = ["K线", "MA5", "MA10", "MA20"];
    if (indicator === "volume") legendData.push("成交量");
    else if (indicator === "macd") legendData.push("DIF", "DEA", "MACD");
    else if (indicator === "rsi") legendData.push("RSI6", "RSI12", "RSI24");

    const option: echarts.EChartsOption = {
      animation: false,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        backgroundColor: "rgba(255, 255, 255, 0.95)",
        borderColor: "#ccc",
        borderWidth: 1,
        textStyle: { color: "#333" },
        formatter: (params: unknown) => {
          const firstParam = Array.isArray(params) ? params[0] : params;
          const idx =
            firstParam && typeof firstParam === "object" && "dataIndex" in firstParam
              ? Number((firstParam as { dataIndex?: unknown }).dataIndex)
              : -1;
          if (!Number.isInteger(idx) || idx < 0 || idx >= klineData.length) return "";
          const item = klineData[idx];
          if (!item) return "";
          const chg = ((item.close - item.open) / item.open * 100).toFixed(2);
          let html = `<div style="padding:8px;font-size:12px;">
            <div style="font-weight:bold;margin-bottom:6px;">${item.date}</div>
            <div>开: <span style="color:${item.close >= item.open ? "#ef4444" : "#22c55e"}">${item.open.toFixed(2)}</span></div>
            <div>高: <span style="color:#ef4444">${item.high.toFixed(2)}</span></div>
            <div>低: <span style="color:#22c55e">${item.low.toFixed(2)}</span></div>
            <div>收: <span style="color:${item.close >= item.open ? "#ef4444" : "#22c55e"}">${item.close.toFixed(2)}</span></div>
            <div>涨跌: <span style="color:${parseFloat(chg) >= 0 ? "#ef4444" : "#22c55e"}">${chg}%</span></div>
            <div>成交量: ${(item.volume / 10000).toFixed(2)}万</div>`;
          if (indicator === "macd" && idx < dif.length && idx < dea.length && idx < macd.length) {
            html += `<div style="margin-top:4px;border-top:1px solid #eee;padding-top:4px;">
              DIF: ${dif[idx].toFixed(3)} | DEA: ${dea[idx].toFixed(3)} | MACD: ${macd[idx].toFixed(3)}
            </div>`;
          } else if (indicator === "rsi" && idx < rsi6.length && idx < rsi12.length && idx < rsi24.length) {
            html += `<div style="margin-top:4px;border-top:1px solid #eee;padding-top:4px;">
              RSI6: ${rsi6[idx].toFixed(1)} | RSI12: ${rsi12[idx].toFixed(1)} | RSI24: ${rsi24[idx].toFixed(1)}
            </div>`;
          }
          html += "</div>";
          return html;
        },
      },
      legend: {
        data: legendData,
        top: 0,
        left: "center",
        textStyle: { fontSize: 11 },
        itemWidth: 14,
        itemHeight: 10,
      },
      grid: grids,
      xAxis: xAxes,
      yAxis: yAxes,
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 },
        { show: true, xAxisIndex: [0, 1], type: "slider", bottom: 5, height: 18, start: 60, end: 100 },
      ],
      series,
    };

    chartInstance.current.setOption(option, true);
  }, [klineData, indicator, calculateMA, calculateMACD, calculateRSI]);

  // 窗口resize
  useEffect(() => {
    const handleResize = () => chartInstance.current?.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
      chartInstance.current?.dispose();
      chartInstance.current = null;
    };
  }, []);

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-4">
          <h3 className="font-medium">K线图</h3>
          {source && <span className="text-xs text-gray-400">来源：{source}</span>}
          {/* 周期切换 */}
          <div className="flex flex-wrap gap-1 text-sm">
            {(oversea
              ? [
                  { key: "day", label: "日K" },
                  { key: "week", label: "周K" },
                  { key: "month", label: "月K" },
                ]
              : [
                  { key: "day", label: "日K" },
                  { key: "week", label: "周K" },
                  { key: "month", label: "月K" },
                  { key: "5min", label: "5m" },
                  { key: "15min", label: "15m" },
                  { key: "30min", label: "30m" },
                  { key: "60min", label: "60m" },
                ]
            ).map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setPeriod(p.key)}
                className={`px-3 py-1 rounded transition-colors ${
                  period === p.key ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {/* 复权切换 */}
        <div className="flex gap-1 text-sm">
          {[
            { key: "qfq", label: "前复权" },
            { key: "hfq", label: "后复权" },
            { key: "none", label: "不复权" },
          ].map((a) => (
            <button
              key={a.key}
              type="button"
              onClick={() => setAdjust(a.key as AdjustType)}
              className={`px-3 py-1 rounded transition-colors ${
                adjust === a.key ? "bg-amber-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
              title="复权设置"
            >
              {a.label}
            </button>
          ))}
        </div>
        {/* 指标切换 */}
        <div className="flex gap-1 text-sm">
          {[
            { key: "volume", label: "成交量" },
            { key: "macd", label: "MACD" },
            { key: "rsi", label: "RSI" },
          ].map((ind) => (
            <button
              key={ind.key}
              type="button"
              onClick={() => setIndicator(ind.key as IndicatorType)}
              className={`px-3 py-1 rounded transition-colors ${
                indicator === ind.key ? "bg-purple-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {ind.label}
            </button>
          ))}
        </div>
      </div>
      {loading && (
        <div className="flex items-center justify-center" style={{ height }}>
          <span className="text-gray-400">加载K线数据...</span>
        </div>
      )}
      {error && (
        <div className="flex items-center justify-center" style={{ height }}>
          <span className="text-red-500">{error}</span>
        </div>
      )}
      {!loading && !error && notice && (
        <div className="flex items-center justify-center" style={{ height }}>
          <span className="text-gray-400">{notice}</span>
        </div>
      )}
      <div ref={chartRef} style={{ height, display: loading || error || notice ? "none" : "block" }} />
    </div>
  );
}
