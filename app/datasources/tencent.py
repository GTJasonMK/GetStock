# Tencent 数据源客户端
"""
腾讯财经数据接口
"""

import re
import json
from typing import List, Any, Optional

import httpx

from app.schemas.stock import KLineResponse, KLineData


class TencentClient:
    """腾讯财经客户端"""

    BASE_URL = "https://web.ifzq.gtimg.cn/appstock/app"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )

    async def close(self):
        await self.client.aclose()

    def _to_float(self, value: Any) -> Optional[float]:
        """尽量把值转换为 float（应对接口字段偶发结构漂移）。"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            try:
                return float(s)
            except (ValueError, TypeError):
                return None

        # 部分网络/代理环境下，接口字段可能被包裹为 dict/list；尽量提取一个可转换的数值
        if isinstance(value, dict):
            for key in ("value", "val", "v", "volume", "amount", "open", "close", "high", "low"):
                if key in value:
                    got = self._to_float(value.get(key))
                    if got is not None:
                        return got
            if len(value) == 1:
                only_val = next(iter(value.values()))
                return self._to_float(only_val)
            return None

        if isinstance(value, (list, tuple)) and len(value) == 1:
            return self._to_float(value[0])

        return None

    def _to_int(self, value: Any) -> Optional[int]:
        """尽量把值转换为 int（用于成交量等字段）。"""
        got = self._to_float(value)
        if got is None:
            return None
        try:
            return int(got)
        except (ValueError, TypeError):
            return None

    def _convert_code(self, code: str) -> str:
        """转换股票代码格式（大小写不敏感）"""
        raw = (code or "").strip()
        if not raw:
            return ""

        lower = raw.lower()
        if lower.startswith(("sh", "sz")):
            return lower
        if lower.startswith("6"):
            return f"sh{lower}"
        if lower.startswith(("0", "3")):
            return f"sz{lower}"
        return lower

    async def get_kline(
        self,
        stock_code: str,
        period: str = "day",
        count: int = 100,
        adjust: str = "qfq",
    ) -> KLineResponse:
        """获取K线数据"""
        code = self._convert_code(stock_code)

        adjust_norm = (adjust or "").strip().lower()
        if adjust_norm != "qfq":
            # 腾讯该接口的复权口径在不同市场/周期下行为差异较大；
            # 为避免“参数可填但实际静默忽略”导致口径错误，这里先显式拒绝非 qfq。
            raise ValueError(f"腾讯K线当前仅支持前复权(qfq)，不支持: {adjust}")

        # 周期映射
        period_map = {
            "day": "day",
            "week": "week",
            "month": "month",
        }
        qq_period = period_map.get(period)
        if not qq_period:
            raise ValueError(f"腾讯K线不支持该周期: {period}")

        # 腾讯 fqkline/get 参数格式：
        #   param=CODE,PERIOD,START_DATE,END_DATE,COUNT,FQTYPE
        # 当不指定日期范围时，需要保留 start/end 两个空段，否则会返回 msg="param error" 且 data=[]
        # 示例：sh600000,day,,,320,qfq
        url = f"{self.BASE_URL}/fqkline/get?_var=kline_data&param={code},{qq_period},,,{count},qfq"
        response = await self.client.get(url)
        content = response.text

        # 解析响应
        match = re.search(r'kline_data=(\{.*\})', content)
        if not match:
            # 该接口在被拦截/限流时可能返回非预期内容，避免后续出现 `'str' object has no attribute 'get'` 这类隐蔽错误
            raise RuntimeError(f"腾讯K线响应格式异常：未找到 kline_data（前200字符）：{content[:200]}")

        try:
            payload = json.loads(match.group(1))
        except Exception as e:
            raise RuntimeError("腾讯K线 JSON 解析失败") from e

        if not isinstance(payload, dict):
            raise RuntimeError(f"腾讯K线 JSON 类型异常：期望 object，实际 {type(payload).__name__}")

        data_field = payload.get("data")
        if not isinstance(data_field, dict):
            msg = payload.get("msg") or payload.get("message") or payload.get("code") or ""
            raise RuntimeError(f"腾讯K线返回异常：data 字段不是对象（type={type(data_field).__name__} msg={msg}）")

        stock_data = data_field.get(code) or {}
        if not isinstance(stock_data, dict):
            raise RuntimeError(f"腾讯K线返回异常：股票数据不是对象（type={type(stock_data).__name__}）")

        kline_data = stock_data.get(qq_period, []) or stock_data.get("qfq" + qq_period, [])
        if not isinstance(kline_data, list):
            raise RuntimeError(f"腾讯K线返回异常：K线数组不是 list（type={type(kline_data).__name__}）")

        klines = []
        for item in kline_data:
            # 兼容两类结构：
            # 1) list: ["YYYY-MM-DD","open","close","high","low","volume", ...]
            # 2) dict: {"date": "...", "open": "...", ...}
            if isinstance(item, dict):
                date = str(item.get("date") or item.get("day") or item.get("time") or "")
                open_val = self._to_float(item.get("open") or item.get("o"))
                close_val = self._to_float(item.get("close") or item.get("c"))
                high_val = self._to_float(item.get("high") or item.get("h"))
                low_val = self._to_float(item.get("low") or item.get("l"))
                volume_val = self._to_int(item.get("volume") or item.get("vol") or item.get("v"))
                amount_val = self._to_float(item.get("amount") or item.get("amt"))
                change_pct_val = self._to_float(item.get("change_percent") or item.get("pct") or item.get("p"))
            elif isinstance(item, (list, tuple)):
                if len(item) < 6:
                    continue
                date = str(item[0] or "")
                open_val = self._to_float(item[1])
                close_val = self._to_float(item[2])
                high_val = self._to_float(item[3])
                low_val = self._to_float(item[4])
                volume_val = self._to_int(item[5])
                amount_val = self._to_float(item[6]) if len(item) > 6 else 0.0
                change_pct_val = self._to_float(item[7]) if len(item) > 7 else 0.0
            else:
                continue

            if not date:
                continue
            if open_val is None or close_val is None or high_val is None or low_val is None or volume_val is None:
                continue

            klines.append(
                KLineData(
                    date=date,
                    open=open_val,
                    close=close_val,
                    high=high_val,
                    low=low_val,
                    volume=volume_val,
                    amount=amount_val or 0.0,
                    change_percent=change_pct_val or 0.0,
                )
            )

        if not klines:
            raise RuntimeError("腾讯K线解析后为空")

        return KLineResponse(
            stock_code=stock_code,
            stock_name=(stock_data.get("qt", {}) or {}).get(code, ["", ""])[1] if isinstance(stock_data.get("qt"), dict) else "",
            period=period,
            data=klines,
        )
