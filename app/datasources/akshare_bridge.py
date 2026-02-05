# AkShare 同步接口桥接（异步封装）
"""
AkShare Bridge

用途：
- 本项目后端基于 FastAPI/asyncio，外部数据源抓取需要避免阻塞事件循环。
- AkShare 大量接口为同步实现（内部 requests + pandas），这里统一用 `asyncio.to_thread` 封装成 async。

设计原则：
- 只做“薄封装”，不自研抓取逻辑；尽量复用 AkShare 生态能力。
- 任何失败都抛出 RuntimeError，由上层 Service 决定是否降级/兜底。
"""

from __future__ import annotations

import asyncio
from typing import Any


def _import_akshare() -> Any:
    try:
        import akshare as ak  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("未安装 akshare，无法使用 AkShare 兜底数据源") from e
    return ak


_AKSHARE_MODULE: Any | None = None
_AKSHARE_LOCK = asyncio.Lock()


async def _get_akshare() -> Any:
    """
    获取 akshare 模块（懒加载 + 线程导入）。

    背景：
    - akshare import 体积较大，首次 import 可能耗时几十秒；
    - 若在事件循环线程中直接 import，会阻塞整个 FastAPI 服务，导致“所有接口卡死”的隐蔽故障。
    """
    global _AKSHARE_MODULE
    if _AKSHARE_MODULE is not None:
        return _AKSHARE_MODULE
    async with _AKSHARE_LOCK:
        if _AKSHARE_MODULE is None:
            _AKSHARE_MODULE = await asyncio.to_thread(_import_akshare)
    return _AKSHARE_MODULE


async def call_akshare(fn_name: str, *args: Any, **kwargs: Any) -> Any:
    """
    以线程方式调用 AkShare 的同步函数。

    Args:
        fn_name: akshare 模块函数名，如 stock_zh_a_spot_em
    """
    ak = await _get_akshare()
    fn = getattr(ak, fn_name, None)
    if not callable(fn):
        raise RuntimeError(f"akshare 不支持该函数: {fn_name}")
    return await asyncio.to_thread(fn, *args, **kwargs)


async def get_a_spot_em_df() -> Any:
    """A股实时行情快照（东方财富口径，DataFrame）"""
    return await call_akshare("stock_zh_a_spot_em")


async def get_board_industry_name_em_df() -> Any:
    """行业板块行情（东方财富口径，DataFrame）"""
    return await call_akshare("stock_board_industry_name_em")


async def get_fund_flow_industry_df(symbol: str = "即时") -> Any:
    """行业资金流（DataFrame）"""
    return await call_akshare("stock_fund_flow_industry", symbol=symbol)


async def get_fund_flow_concept_df(symbol: str = "即时") -> Any:
    """概念资金流（DataFrame）"""
    return await call_akshare("stock_fund_flow_concept", symbol=symbol)


async def get_hsgt_hist_em_df(symbol: str = "北向资金") -> Any:
    """沪深港通历史资金（DataFrame）"""
    return await call_akshare("stock_hsgt_hist_em", symbol=symbol)


async def get_long_tiger_detail_em_df(start_date: str, end_date: str) -> Any:
    """龙虎榜明细（东方财富口径，DataFrame；日期格式 YYYYMMDD）"""
    return await call_akshare("stock_lhb_detail_em", start_date=start_date, end_date=end_date)


async def get_news_main_cx_df() -> Any:
    """财新主要新闻（DataFrame：tag/summary/url）"""
    return await call_akshare("stock_news_main_cx")
