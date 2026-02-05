# Utils 工具函数
"""
通用工具函数
"""

from datetime import datetime, date, timedelta
from functools import lru_cache
from typing import Optional
import re

from zoneinfo import ZoneInfo

from app.config import get_settings


def format_number(value: float, precision: int = 2) -> str:
    """格式化数字，添加千分位"""
    if abs(value) >= 100000000:
        return f"{value / 100000000:.{precision}f}亿"
    elif abs(value) >= 10000:
        return f"{value / 10000:.{precision}f}万"
    else:
        return f"{value:.{precision}f}"


def parse_stock_code(code: str) -> tuple:
    """
    解析股票代码
    返回 (market, code) 如 ('sh', '600000')
    """
    code = (code or "").strip()
    if not code:
        return "", ""

    lower = code.lower()

    # 市场前缀（大小写不敏感）
    if lower.startswith("sh"):
        return "sh", lower[2:]
    if lower.startswith("sz"):
        return "sz", lower[2:]
    if lower.startswith("hk"):
        return "hk", lower[2:]
    if lower.startswith("us"):
        # 美股 ticker 建议保持大写，便于与外部数据源一致
        return "us", code[2:].strip().upper()

    # 纯数字代码：自动判断交易所（仅覆盖项目当前主要支持的 A 股）
    if lower.isdigit():
        if lower.startswith("6"):
            return "sh", lower
        if lower.startswith(("0", "3")):
            return "sz", lower

    return "", code


def normalize_stock_code(code: str) -> str:
    """
    标准化股票代码
    返回带市场前缀的代码，如 sh600000
    """
    market, pure_code = parse_stock_code(code)
    if not market:
        return (code or "").strip()
    return f"{market}{pure_code}"


@lru_cache
def get_market_timezone() -> ZoneInfo:
    """获取市场时区（用于交易时段判断与 scheduler）"""
    tz_name = (get_settings().market_timezone or "Asia/Shanghai").strip()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def _is_china_market_holiday(day: date) -> bool:
    """
    判断日期是否为中国法定节假日/休市日（可选依赖）。

    说明：
    - 交易模块对“休市日误触发”比较敏感，但维护完整交易日历属于重维护面；
      因此这里优先复用生态库 `chinese-calendar`，缺依赖时退化为“不判断节假日”。
    """
    try:
        from chinese_calendar import is_holiday  # type: ignore

        return bool(is_holiday(day))
    except Exception:
        return False


def is_trading_day(day: date, tz: Optional[ZoneInfo] = None) -> bool:
    """
    判断某天是否为交易日。

    当前策略（偏谨慎、低维护面）：
    - 周六/周日：一定不交易
    - 中国市场时区（Asia/Shanghai/Asia/Hong_Kong）：若为法定节假日则视为休市
    - 其他时区：暂不做节假日判断（避免错误地把其他市场的“正常交易日”判为休市）
    """
    if day.weekday() >= 5:
        return False

    if tz is not None:
        tz_key = getattr(tz, "key", "")
        if tz_key not in {"Asia/Shanghai", "Asia/Hong_Kong"}:
            return True

    if _is_china_market_holiday(day):
        return False

    return True


def is_trading_time(now: Optional[datetime] = None) -> bool:
    """判断当前是否为交易时间"""
    tz = get_market_timezone()
    if now is None:
        now = datetime.now(tz)
    else:
        # 兼容历史用法：传入 naive datetime 时，默认视为“市场时区时间”
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        else:
            now = now.astimezone(tz)

    # 交易日判断（含可选节假日休市判断）
    if not is_trading_day(now.date(), tz=tz):
        return False

    # 上午 9:30-11:30, 下午 13:00-15:00
    current_time = now.time()
    morning_start = datetime.strptime("09:30", "%H:%M").time()
    morning_end = datetime.strptime("11:30", "%H:%M").time()
    afternoon_start = datetime.strptime("13:00", "%H:%M").time()
    afternoon_end = datetime.strptime("15:00", "%H:%M").time()

    if morning_start <= current_time <= morning_end:
        return True
    if afternoon_start <= current_time <= afternoon_end:
        return True

    return False


def get_last_trading_date(reference: Optional[date] = None, tz: Optional[ZoneInfo] = None) -> str:
    """
    获取最近交易日（包含节假日休市判断）。

    说明：
    - 仅回溯自然日，直到命中 `is_trading_day()` 为 True；
    - 默认使用市场时区（`get_market_timezone()`）的“今天”作为参考点；
    - 该函数会被龙虎榜/调度器等模块复用，用于避免取到“无数据日期”。
    """
    market_tz = tz or get_market_timezone()
    day = reference or datetime.now(market_tz).date()

    # 取一个足够大的回溯窗口，避免长假导致死循环
    for _ in range(30):
        if is_trading_day(day, tz=market_tz):
            return day.strftime("%Y-%m-%d")
        day = day - timedelta(days=1)

    # 兜底：极端情况下仍返回回溯后的日期
    return day.strftime("%Y-%m-%d")


def extract_json(text: str) -> Optional[dict]:
    """从文本中提取JSON"""
    import json

    # 尝试直接解析
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试从```json```代码块提取
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # 尝试从{...}提取
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except (json.JSONDecodeError, TypeError):
            pass

    return None
