# 筹码分布数据源（对标 daily_stock_analysis 的 ChipDistribution）
"""
筹码分布数据获取

设计目标：
- 复用生态库 `akshare` 的 `stock_cyq_em`，避免自研/重复实现筹码算法
- 在 async Web 服务中以线程方式运行阻塞调用，避免阻塞事件循环
- 统一输出字段：获利比例、平均成本、70/90 成本区间与集中度

参考：
- daily_stock_analysis: data_provider/akshare_fetcher.py:get_chip_distribution()
- akshare: stock_cyq_em()
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _normalize_ratio(val: Any) -> float:
    """
    归一化比例字段到 0-1。

    akshare 可能返回：
    - 0.35（已是 0-1）
    - 35（百分数）
    """
    f = _safe_float(val, default=0.0)
    if f > 1:
        f = f / 100.0
    if f < 0:
        return 0.0
    return f


async def fetch_chip_distribution_em(symbol: str) -> Optional[Dict[str, Any]]:
    """
    获取单只股票最新筹码分布数据（东方财富口径，akshare 计算）

    Args:
        symbol: 纯数字股票代码，如 600519 / 000001（不要带 sh/sz 前缀）

    Returns:
        dict 或 None（无数据/ETF/指数等）。

    Raises:
        RuntimeError: 未安装 akshare 或调用失败
    """
    try:
        import akshare as ak  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("未安装 akshare，无法获取筹码分布") from e

    # akshare 内部包含同步网络请求与 JS 计算，必须放到线程执行
    try:
        df = await asyncio.to_thread(ak.stock_cyq_em, symbol=symbol)
    except Exception as e:
        raise RuntimeError(f"akshare 获取筹码分布失败: {e}") from e

    if df is None or getattr(df, "empty", True):
        return None

    try:
        latest = df.iloc[-1]
    except Exception:
        return None

    # pandas Series.get() 可用；若不是则降级用索引
    def _get(key: str) -> Any:
        try:
            return latest.get(key)  # type: ignore[attr-defined]
        except Exception:
            try:
                return latest[key]  # type: ignore[index]
            except Exception:
                return None

    return {
        "date": str(_get("日期") or ""),
        "profit_ratio": _normalize_ratio(_get("获利比例")),
        "avg_cost": _safe_float(_get("平均成本")),
        "cost_90_low": _safe_float(_get("90成本-低")),
        "cost_90_high": _safe_float(_get("90成本-高")),
        "concentration_90": _normalize_ratio(_get("90集中度")),
        "cost_70_low": _safe_float(_get("70成本-低")),
        "cost_70_high": _safe_float(_get("70成本-高")),
        "concentration_70": _normalize_ratio(_get("70集中度")),
        "source": "akshare",
    }

