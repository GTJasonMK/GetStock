# AkShare 数据源客户端（用于港股/美股 K 线兜底）
"""
AkShare Client

目标：
- 复用生态库 akshare 的海外市场 K 线能力（港股/美股），补齐当前项目在 hk/us 的 K 线与技术分析链路；
- 避免在 async Web 服务中阻塞事件循环：通过 `app.datasources.akshare_bridge` 线程封装调用；
- 输出统一的 `KLineResponse` 结构，供前端 K 线图与技术分析复用。

注意：
- A 股 K 线本项目优先走腾讯/东财（更轻量且支持分钟周期），这里仅负责 hk/us day/week/month；
- 美股 K 线接口需要 Eastmoney 的 secid（如 105.MSFT），需先通过 `ak.stock_us_spot_em()` 做 ticker→secid 映射；
  该映射会做内存缓存（TTL 24h），避免每次请求都拉取全量美股列表。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from app.datasources.akshare_bridge import call_akshare
from app.schemas.stock import KLineData, KLineResponse
from app.utils.helpers import parse_stock_code

logger = logging.getLogger(__name__)


def _to_float(val: Any, default: float | None = None) -> float | None:
    try:
        if val is None:
            return default
        if isinstance(val, bool):
            return default
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            s = val.strip()
            if not s or s in {"-", "--"}:
                return default
            return float(s)
        return default
    except Exception:
        return default


def _to_int(val: Any, default: int = 0) -> int:
    f = _to_float(val, default=None)
    if f is None:
        return default
    try:
        return int(f)
    except Exception:
        return default


def _df_is_empty(df: object) -> bool:
    try:
        return df is None or bool(getattr(df, "empty"))  # type: ignore[attr-defined]
    except Exception:
        return df is None


def _norm_us_ticker(ticker: str) -> str:
    # Eastmoney 可能用 '-' 表示类别股，这里统一成 '.'，与常见 ticker 表达一致
    return (ticker or "").strip().upper().replace("-", ".")


_US_SECID_CACHE_TTL_SECONDS = 24 * 60 * 60
_US_SECID_CACHE_LOCK = asyncio.Lock()
_US_TICKER_TO_SECID: Dict[str, str] = {}
_US_SECID_CACHE_EXPIRES_AT: float = 0.0


async def _resolve_us_secid(ticker: str) -> str:
    """
    将美股 ticker（如 AAPL / BRK.B）映射为 Eastmoney secid（如 105.MSFT）。

    akshare 的 `stock_us_hist` 要求 symbol 为 secid；我们在此做缓存映射。
    """
    wanted = _norm_us_ticker(ticker)
    if not wanted:
        raise ValueError("美股 ticker 不能为空")

    now = time.time()
    if now < _US_SECID_CACHE_EXPIRES_AT:
        cached = _US_TICKER_TO_SECID.get(wanted)
        if cached:
            return cached

    async with _US_SECID_CACHE_LOCK:
        now = time.time()
        if now < _US_SECID_CACHE_EXPIRES_AT:
            cached = _US_TICKER_TO_SECID.get(wanted)
            if cached:
                return cached

        # 拉取美股列表并建立映射（代价较高，务必缓存）
        df = await call_akshare("stock_us_spot_em")
        if _df_is_empty(df):
            raise RuntimeError("AkShare 美股列表为空，无法解析 secid")

        mapping: Dict[str, str] = {}
        try:
            records = df.to_dict("records")  # type: ignore[call-arg]
        except Exception:
            records = []

        for r in records or []:
            if not isinstance(r, dict):
                continue
            secid = str(r.get("代码", "") or "").strip()
            if not secid:
                continue
            if "." in secid:
                _, t = secid.split(".", 1)
            else:
                t = secid
            key = _norm_us_ticker(t)
            if key:
                mapping[key] = secid

        _US_TICKER_TO_SECID.clear()
        _US_TICKER_TO_SECID.update(mapping)
        _US_SECID_CACHE_EXPIRES_AT = time.time() + _US_SECID_CACHE_TTL_SECONDS

        resolved = _US_TICKER_TO_SECID.get(wanted)
        if not resolved:
            raise ValueError(f"无法识别美股 ticker: {ticker}（未在 Eastmoney 列表中找到）")
        return resolved


class AkShareClient:
    """AkShare 数据源客户端（当前仅提供 hk/us 的日/周/月 K 线）。"""

    async def get_kline(
        self,
        stock_code: str,
        period: str = "day",
        count: int = 100,
        adjust: str = "qfq",
    ) -> KLineResponse:
        market, pure_code = parse_stock_code(stock_code)

        period_map = {"day": "daily", "week": "weekly", "month": "monthly"}
        ak_period = period_map.get((period or "").strip().lower())
        if not ak_period:
            raise ValueError("AkShare(hk/us) K线仅支持 day/week/month")

        adjust_norm = (adjust or "").strip().lower()
        adjust_map = {"qfq": "qfq", "hfq": "hfq", "none": "", "": ""}
        ak_adjust = adjust_map.get(adjust_norm)
        if ak_adjust is None:
            raise ValueError(f"AkShare(hk/us) 不支持该复权类型: {adjust}")

        df = None
        stock_name = ""

        if market == "hk":
            # 港股代码统一补齐 5 位（00700）
            symbol = (pure_code or "").strip()
            if symbol.isdigit():
                symbol = symbol.zfill(5)
            df = await call_akshare("stock_hk_hist", symbol=symbol, period=ak_period, adjust=ak_adjust)
        elif market == "us":
            ticker = (pure_code or "").strip().upper()
            secid = await _resolve_us_secid(ticker)
            stock_name = ticker
            df = await call_akshare("stock_us_hist", symbol=secid, period=ak_period, adjust=ak_adjust)
        else:
            raise ValueError("AkShareClient 当前仅支持港股(hk)/美股(us) K线")

        if _df_is_empty(df):
            raise RuntimeError("AkShare K线返回为空")

        try:
            df = df.tail(max(1, int(count)))  # type: ignore[union-attr]
        except Exception:
            pass

        try:
            records = df.to_dict("records")  # type: ignore[call-arg]
        except Exception as e:
            raise RuntimeError(f"AkShare K线解析失败: {e}") from e

        klines: list[KLineData] = []
        for r in records or []:
            if not isinstance(r, dict):
                continue

            date = str(r.get("日期", "") or "")
            open_val = _to_float(r.get("开盘"), default=None)
            close_val = _to_float(r.get("收盘"), default=None)
            high_val = _to_float(r.get("最高"), default=None)
            low_val = _to_float(r.get("最低"), default=None)
            volume_val = _to_int(r.get("成交量"), default=0)
            amount_val = _to_float(r.get("成交额"), default=0.0) or 0.0
            change_pct = _to_float(r.get("涨跌幅"), default=0.0) or 0.0

            if not date or open_val is None or close_val is None or high_val is None or low_val is None:
                continue

            klines.append(
                KLineData(
                    date=date,
                    open=float(open_val),
                    close=float(close_val),
                    high=float(high_val),
                    low=float(low_val),
                    volume=int(volume_val),
                    amount=float(amount_val),
                    change_percent=float(change_pct),
                )
            )

        if not klines:
            raise RuntimeError("AkShare K线解析后为空")

        return KLineResponse(
            stock_code=stock_code,
            stock_name=stock_name,
            period=(period or "").strip().lower(),
            data=klines,
        )

