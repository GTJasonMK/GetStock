# 技术分析服务
"""
股票技术分析服务 - 提供MACD、RSI、趋势分析和买卖信号评分
"""

import logging
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """趋势状态 - 7级分类"""
    STRONG_UP = "strong_up"           # 强势上涨
    UP = "up"                         # 上涨
    WEAK_UP = "weak_up"              # 弱势上涨
    CONSOLIDATION = "consolidation"   # 震荡整理
    WEAK_DOWN = "weak_down"          # 弱势下跌
    DOWN = "down"                     # 下跌
    STRONG_DOWN = "strong_down"       # 强势下跌


class BuySignal(Enum):
    """买卖信号 - 7级分类"""
    STRONG_BUY = "strong_buy"         # 强烈买入 (80-100分)
    BUY = "buy"                       # 买入 (65-79分)
    WEAK_BUY = "weak_buy"            # 弱买入 (55-64分)
    HOLD = "hold"                     # 持有/观望 (45-54分)
    WEAK_SELL = "weak_sell"          # 弱卖出 (35-44分)
    SELL = "sell"                     # 卖出 (20-34分)
    STRONG_SELL = "strong_sell"       # 强烈卖出 (0-19分)


class MACDSignal(Enum):
    """MACD信号"""
    GOLDEN_CROSS = "golden_cross"     # 金叉
    DEATH_CROSS = "death_cross"       # 死叉
    BULLISH = "bullish"               # 多头
    BEARISH = "bearish"               # 空头
    NEUTRAL = "neutral"               # 中性


class RSISignal(Enum):
    """RSI信号"""
    OVERSOLD = "oversold"             # 超卖 (<30)
    OVERBOUGHT = "overbought"         # 超买 (>70)
    NEUTRAL = "neutral"               # 中性


@dataclass
class MACDResult:
    """MACD计算结果"""
    dif: float                # 快线
    dea: float                # 慢线
    macd: float               # MACD柱
    signal: MACDSignal        # 信号
    dif_history: List[float]  # 历史DIF值
    dea_history: List[float]  # 历史DEA值
    macd_history: List[float] # 历史MACD值


@dataclass
class RSIResult:
    """RSI计算结果"""
    rsi_6: float              # 6日RSI
    rsi_12: float             # 12日RSI
    rsi_24: float             # 24日RSI
    signal: RSISignal         # 信号


@dataclass
class VolumeAnalysis:
    """成交量分析结果"""
    current_volume: int           # 当日成交量
    avg_volume_5: float           # 5日均量
    avg_volume_10: float          # 10日均量
    volume_ratio: float           # 量比 (当日成交量/5日均量)
    is_volume_breakout: bool      # 是否放量突破
    volume_trend: str             # 成交量趋势: "increasing", "decreasing", "stable"


@dataclass
class TrendAnalysis:
    """趋势分析结果"""
    status: TrendStatus           # 趋势状态
    ma_5: float                   # 5日均线
    ma_10: float                  # 10日均线
    ma_20: float                  # 20日均线
    ma_60: float                  # 60日均线
    price_position: str           # 价格位置: "above_all", "above_short", "below_all", "mixed"
    ma_alignment: str             # 均线排列: "bullish", "bearish", "mixed"
    bias_5: float                 # 5日乖离率
    bias_10: float                # 10日乖离率


@dataclass
class SupportResistance:
    """支撑阻力位"""
    support_1: float              # 第一支撑位
    support_2: float              # 第二支撑位
    resistance_1: float           # 第一阻力位
    resistance_2: float           # 第二阻力位
    current_price: float          # 当前价格
    distance_to_support: float    # 距支撑位百分比
    distance_to_resistance: float # 距阻力位百分比


@dataclass
class TechnicalAnalysisResult:
    """技术分析完整结果"""
    code: str
    name: str
    current_price: float
    change_percent: float
    trend: TrendAnalysis
    macd: MACDResult
    rsi: RSIResult
    volume: VolumeAnalysis
    support_resistance: SupportResistance
    buy_signal: BuySignal
    score: int                    # 综合评分 0-100
    score_details: Dict[str, int] # 评分明细
    analysis_time: datetime
    summary: str                  # 分析摘要


class TechnicalService:
    """技术分析服务"""

    # MACD参数
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9

    # RSI周期
    RSI_PERIODS = [6, 12, 24]

    # 评分权重
    SCORE_WEIGHTS = {
        "trend": 30,      # 趋势: 30分
        "bias": 20,       # 乖离率: 20分
        "volume": 15,     # 成交量: 15分
        "support": 10,    # 支撑位: 10分
        "macd": 15,       # MACD: 15分
        "rsi": 10,        # RSI: 10分
    }

    def __init__(self):
        pass

    async def analyze(
        self,
        code: str,
        klines: List[Dict],
        stock_name: str = "",
    ) -> TechnicalAnalysisResult:
        """
        完整技术分析

        Args:
            code: 股票代码
            klines: K线数据列表，每项包含 date, open, close, high, low, volume
            stock_name: 股票名称

        Returns:
            TechnicalAnalysisResult: 完整分析结果
        """
        if len(klines) < 60:
            raise ValueError(f"K线数据不足，需要至少60条，当前: {len(klines)}")

        # 提取价格和成交量序列
        closes = [float(k.get("close", 0)) for k in klines]
        highs = [float(k.get("high", 0)) for k in klines]
        lows = [float(k.get("low", 0)) for k in klines]
        volumes = [int(k.get("volume", 0)) for k in klines]

        current_price = closes[-1]
        prev_close = closes[-2] if len(closes) > 1 else current_price
        change_percent = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0

        # 计算各项指标
        macd_result = self.calculate_macd(closes)
        rsi_result = self.calculate_rsi(closes)
        trend_result = self.analyze_trend(closes, current_price)
        volume_result = self.analyze_volume(volumes)
        support_resistance = self.calculate_support_resistance(highs, lows, current_price)

        # 计算综合评分
        score, score_details = self.calculate_score(
            trend_result,
            macd_result,
            rsi_result,
            volume_result,
            support_resistance,
        )

        # 确定买卖信号
        buy_signal = self._score_to_signal(score)

        # 生成分析摘要
        summary = self._generate_summary(
            trend_result,
            macd_result,
            rsi_result,
            volume_result,
            buy_signal,
            score,
        )

        return TechnicalAnalysisResult(
            code=code,
            name=stock_name,
            current_price=current_price,
            change_percent=change_percent,
            trend=trend_result,
            macd=macd_result,
            rsi=rsi_result,
            volume=volume_result,
            support_resistance=support_resistance,
            buy_signal=buy_signal,
            score=score,
            score_details=score_details,
            analysis_time=datetime.now(),
            summary=summary,
        )

    def calculate_macd(self, prices: List[float]) -> MACDResult:
        """
        计算MACD指标

        MACD = DIF - DEA
        DIF = EMA(12) - EMA(26)
        DEA = EMA(DIF, 9)
        """
        # 计算EMA
        ema_fast = self._calculate_ema(prices, self.MACD_FAST)
        ema_slow = self._calculate_ema(prices, self.MACD_SLOW)

        # 计算DIF
        dif_list = []
        for i in range(len(prices)):
            if i < self.MACD_SLOW - 1:
                dif_list.append(0)
            else:
                dif_list.append(ema_fast[i] - ema_slow[i])

        # 计算DEA (DIF的EMA)
        dea_list = self._calculate_ema(dif_list, self.MACD_SIGNAL)

        # 计算MACD柱
        macd_list = []
        for i in range(len(prices)):
            macd_list.append((dif_list[i] - dea_list[i]) * 2)

        # 当前值
        dif = round(dif_list[-1], 3)
        dea = round(dea_list[-1], 3)
        macd = round(macd_list[-1], 3)

        # 判断信号
        signal = self._determine_macd_signal(dif_list, dea_list, macd_list)

        return MACDResult(
            dif=dif,
            dea=dea,
            macd=macd,
            signal=signal,
            dif_history=dif_list[-30:],
            dea_history=dea_list[-30:],
            macd_history=macd_list[-30:],
        )

    def calculate_rsi(
        self,
        prices: List[float],
        periods: Optional[List[int]] = None,
    ) -> RSIResult:
        """
        计算RSI指标

        RSI = 100 - 100 / (1 + RS)
        RS = 平均上涨幅度 / 平均下跌幅度
        """
        periods = periods or self.RSI_PERIODS

        results = {}
        for period in periods:
            rsi = self._calculate_single_rsi(prices, period)
            results[period] = round(rsi, 2)

        # 使用RSI6判断信号
        rsi_6 = results.get(6, 50)
        if rsi_6 < 30:
            signal = RSISignal.OVERSOLD
        elif rsi_6 > 70:
            signal = RSISignal.OVERBOUGHT
        else:
            signal = RSISignal.NEUTRAL

        return RSIResult(
            rsi_6=results.get(6, 50),
            rsi_12=results.get(12, 50),
            rsi_24=results.get(24, 50),
            signal=signal,
        )

    def analyze_trend(self, prices: List[float], current_price: float) -> TrendAnalysis:
        """分析趋势"""
        # 计算均线
        ma_5 = self._calculate_ma(prices, 5)
        ma_10 = self._calculate_ma(prices, 10)
        ma_20 = self._calculate_ma(prices, 20)
        ma_60 = self._calculate_ma(prices, 60)

        # 计算乖离率
        bias_5 = round((current_price - ma_5) / ma_5 * 100, 2) if ma_5 > 0 else 0
        bias_10 = round((current_price - ma_10) / ma_10 * 100, 2) if ma_10 > 0 else 0

        # 判断价格位置
        price_position = self._determine_price_position(current_price, ma_5, ma_10, ma_20, ma_60)

        # 判断均线排列
        ma_alignment = self._determine_ma_alignment(ma_5, ma_10, ma_20, ma_60)

        # 综合判断趋势状态
        status = self._determine_trend_status(price_position, ma_alignment, bias_5, prices)

        return TrendAnalysis(
            status=status,
            ma_5=round(ma_5, 2),
            ma_10=round(ma_10, 2),
            ma_20=round(ma_20, 2),
            ma_60=round(ma_60, 2),
            price_position=price_position,
            ma_alignment=ma_alignment,
            bias_5=bias_5,
            bias_10=bias_10,
        )

    def analyze_volume(self, volumes: List[float]) -> VolumeAnalysis:
        """分析成交量"""
        current_volume = int(volumes[-1])
        avg_5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
        avg_10 = sum(volumes[-10:]) / 10 if len(volumes) >= 10 else volumes[-1]

        # 量比
        volume_ratio = round(current_volume / avg_5, 2) if avg_5 > 0 else 1

        # 是否放量 (量比>1.5)
        is_breakout = volume_ratio > 1.5

        # 成交量趋势
        if len(volumes) >= 5:
            recent_avg = sum(volumes[-3:]) / 3
            previous_avg = sum(volumes[-6:-3]) / 3 if len(volumes) >= 6 else recent_avg
            if recent_avg > previous_avg * 1.2:
                trend = "increasing"
            elif recent_avg < previous_avg * 0.8:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return VolumeAnalysis(
            current_volume=current_volume,
            avg_volume_5=round(avg_5, 0),
            avg_volume_10=round(avg_10, 0),
            volume_ratio=volume_ratio,
            is_volume_breakout=is_breakout,
            volume_trend=trend,
        )

    def calculate_support_resistance(
        self,
        highs: List[float],
        lows: List[float],
        current_price: float,
    ) -> SupportResistance:
        """计算支撑阻力位"""
        # 使用最近20日的高低点
        recent_highs = highs[-20:]
        recent_lows = lows[-20:]

        # 排序找出关键价位
        sorted_highs = sorted(set(recent_highs), reverse=True)
        sorted_lows = sorted(set(recent_lows))

        # 阻力位: 高于当前价格的高点
        resistances = [h for h in sorted_highs if h > current_price]
        resistance_1 = resistances[0] if resistances else current_price * 1.05
        resistance_2 = resistances[1] if len(resistances) > 1 else resistance_1 * 1.03

        # 支撑位: 低于当前价格的低点
        supports = [l for l in sorted_lows if l < current_price]
        support_1 = supports[-1] if supports else current_price * 0.95
        support_2 = supports[-2] if len(supports) > 1 else support_1 * 0.97

        # 距离百分比
        dist_support = round((current_price - support_1) / current_price * 100, 2)
        dist_resistance = round((resistance_1 - current_price) / current_price * 100, 2)

        return SupportResistance(
            support_1=round(support_1, 2),
            support_2=round(support_2, 2),
            resistance_1=round(resistance_1, 2),
            resistance_2=round(resistance_2, 2),
            current_price=round(current_price, 2),
            distance_to_support=dist_support,
            distance_to_resistance=dist_resistance,
        )

    def calculate_score(
        self,
        trend: TrendAnalysis,
        macd: MACDResult,
        rsi: RSIResult,
        volume: VolumeAnalysis,
        support: SupportResistance,
    ) -> Tuple[int, Dict[str, int]]:
        """
        计算综合评分 (满分100)

        评分维度:
        - 趋势: 30分
        - 乖离率: 20分
        - 成交量: 15分
        - 支撑位: 10分
        - MACD: 15分
        - RSI: 10分
        """
        details = {}

        # 1. 趋势评分 (30分)
        trend_scores = {
            TrendStatus.STRONG_UP: 30,
            TrendStatus.UP: 25,
            TrendStatus.WEAK_UP: 20,
            TrendStatus.CONSOLIDATION: 15,
            TrendStatus.WEAK_DOWN: 10,
            TrendStatus.DOWN: 5,
            TrendStatus.STRONG_DOWN: 0,
        }
        details["trend"] = trend_scores.get(trend.status, 15)

        # 2. 乖离率评分 (20分)
        # 乖离率适中为佳，过大过小都减分
        bias = abs(trend.bias_5)
        if bias < 3:
            details["bias"] = 20  # 乖离率小，安全
        elif bias < 5:
            details["bias"] = 15
        elif bias < 8:
            details["bias"] = 10
        else:
            details["bias"] = 5  # 乖离率过大，风险高

        # 3. 成交量评分 (15分)
        if volume.is_volume_breakout and trend.status in [TrendStatus.STRONG_UP, TrendStatus.UP, TrendStatus.WEAK_UP]:
            details["volume"] = 15  # 上涨放量，最佳
        elif volume.volume_ratio > 1.0:
            details["volume"] = 10
        elif volume.volume_ratio > 0.7:
            details["volume"] = 7
        else:
            details["volume"] = 3  # 缩量

        # 4. 支撑位评分 (10分)
        if support.distance_to_support < 2:
            details["support"] = 10  # 接近支撑位，买点
        elif support.distance_to_support < 5:
            details["support"] = 7
        elif support.distance_to_resistance < 2:
            details["support"] = 3  # 接近阻力位，卖点
        else:
            details["support"] = 5

        # 5. MACD评分 (15分)
        macd_scores = {
            MACDSignal.GOLDEN_CROSS: 15,
            MACDSignal.BULLISH: 12,
            MACDSignal.NEUTRAL: 8,
            MACDSignal.BEARISH: 4,
            MACDSignal.DEATH_CROSS: 0,
        }
        details["macd"] = macd_scores.get(macd.signal, 8)

        # 6. RSI评分 (10分)
        if rsi.signal == RSISignal.OVERSOLD:
            details["rsi"] = 10  # 超卖，可能反弹
        elif rsi.signal == RSISignal.OVERBOUGHT:
            details["rsi"] = 2  # 超买，可能回调
        else:
            # 中性区间，根据具体值给分
            if 40 <= rsi.rsi_6 <= 60:
                details["rsi"] = 7
            elif 30 <= rsi.rsi_6 <= 70:
                details["rsi"] = 5
            else:
                details["rsi"] = 3

        total = sum(details.values())
        return total, details

    # ============ 私有方法 ============

    def _calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """计算指数移动平均线"""
        ema = []
        multiplier = 2 / (period + 1)

        for i, price in enumerate(prices):
            if i == 0:
                ema.append(price)
            else:
                ema.append((price - ema[-1]) * multiplier + ema[-1])

        return ema

    def _calculate_ma(self, prices: List[float], period: int) -> float:
        """计算简单移动平均线"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        return sum(prices[-period:]) / period

    def _calculate_single_rsi(self, prices: List[float], period: int) -> float:
        """计算单个周期的RSI"""
        if len(prices) < period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        # 使用最近period天的数据
        recent_gains = gains[-period:]
        recent_losses = losses[-period:]

        avg_gain = sum(recent_gains) / period
        avg_loss = sum(recent_losses) / period

        if avg_loss == 0:
            # 既没有上涨也没有下跌（横盘）时，RSI 应为 50；全为上涨时才为 100
            return 50 if avg_gain == 0 else 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _determine_macd_signal(
        self,
        dif_list: List[float],
        dea_list: List[float],
        macd_list: List[float],
    ) -> MACDSignal:
        """判断MACD信号"""
        if len(dif_list) < 2 or len(dea_list) < 2:
            return MACDSignal.NEUTRAL

        # 当前和前一天的DIF、DEA
        dif_curr = dif_list[-1]
        dif_prev = dif_list[-2]
        dea_curr = dea_list[-1]
        dea_prev = dea_list[-2]

        # 金叉: DIF从下向上穿越DEA
        if dif_prev <= dea_prev and dif_curr > dea_curr:
            return MACDSignal.GOLDEN_CROSS

        # 死叉: DIF从上向下穿越DEA
        if dif_prev >= dea_prev and dif_curr < dea_curr:
            return MACDSignal.DEATH_CROSS

        # 多头: DIF在DEA上方
        if dif_curr > dea_curr:
            return MACDSignal.BULLISH

        # 空头: DIF在DEA下方
        if dif_curr < dea_curr:
            return MACDSignal.BEARISH

        return MACDSignal.NEUTRAL

    def _determine_price_position(
        self,
        price: float,
        ma_5: float,
        ma_10: float,
        ma_20: float,
        ma_60: float,
    ) -> str:
        """判断价格相对均线的位置"""
        above_count = 0
        if price > ma_5:
            above_count += 1
        if price > ma_10:
            above_count += 1
        if price > ma_20:
            above_count += 1
        if price > ma_60:
            above_count += 1

        if above_count == 4:
            return "above_all"
        elif above_count >= 2:
            return "above_short"
        elif above_count == 0:
            return "below_all"
        else:
            return "mixed"

    def _determine_ma_alignment(
        self,
        ma_5: float,
        ma_10: float,
        ma_20: float,
        ma_60: float,
    ) -> str:
        """判断均线排列"""
        if ma_5 > ma_10 > ma_20 > ma_60:
            return "bullish"  # 多头排列
        elif ma_5 < ma_10 < ma_20 < ma_60:
            return "bearish"  # 空头排列
        else:
            return "mixed"  # 混乱排列

    def _determine_trend_status(
        self,
        price_position: str,
        ma_alignment: str,
        bias_5: float,
        prices: List[float],
    ) -> TrendStatus:
        """综合判断趋势状态"""
        # 计算最近5日涨幅
        recent_change = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices) >= 5 and prices[-5] > 0 else 0

        if ma_alignment == "bullish" and price_position == "above_all":
            if recent_change > 5:
                return TrendStatus.STRONG_UP
            return TrendStatus.UP
        elif ma_alignment == "bullish" and price_position == "above_short":
            return TrendStatus.WEAK_UP
        elif ma_alignment == "bearish" and price_position == "below_all":
            if recent_change < -5:
                return TrendStatus.STRONG_DOWN
            return TrendStatus.DOWN
        elif ma_alignment == "bearish" and price_position in ["mixed", "above_short"]:
            return TrendStatus.WEAK_DOWN
        else:
            return TrendStatus.CONSOLIDATION

    def _score_to_signal(self, score: int) -> BuySignal:
        """将评分转换为买卖信号"""
        if score >= 80:
            return BuySignal.STRONG_BUY
        elif score >= 65:
            return BuySignal.BUY
        elif score >= 55:
            return BuySignal.WEAK_BUY
        elif score >= 45:
            return BuySignal.HOLD
        elif score >= 35:
            return BuySignal.WEAK_SELL
        elif score >= 20:
            return BuySignal.SELL
        else:
            return BuySignal.STRONG_SELL

    def _generate_summary(
        self,
        trend: TrendAnalysis,
        macd: MACDResult,
        rsi: RSIResult,
        volume: VolumeAnalysis,
        signal: BuySignal,
        score: int,
    ) -> str:
        """生成分析摘要"""
        parts = []

        # 趋势描述
        trend_desc = {
            TrendStatus.STRONG_UP: "强势上涨趋势",
            TrendStatus.UP: "上涨趋势",
            TrendStatus.WEAK_UP: "弱势上涨",
            TrendStatus.CONSOLIDATION: "震荡整理",
            TrendStatus.WEAK_DOWN: "弱势下跌",
            TrendStatus.DOWN: "下跌趋势",
            TrendStatus.STRONG_DOWN: "强势下跌趋势",
        }
        parts.append(f"当前处于{trend_desc.get(trend.status, '震荡')}")

        # 均线排列
        if trend.ma_alignment == "bullish":
            parts.append("均线多头排列")
        elif trend.ma_alignment == "bearish":
            parts.append("均线空头排列")

        # MACD信号
        macd_desc = {
            MACDSignal.GOLDEN_CROSS: "MACD金叉",
            MACDSignal.DEATH_CROSS: "MACD死叉",
            MACDSignal.BULLISH: "MACD多头",
            MACDSignal.BEARISH: "MACD空头",
        }
        if macd.signal in macd_desc:
            parts.append(macd_desc[macd.signal])

        # RSI信号
        if rsi.signal == RSISignal.OVERSOLD:
            parts.append("RSI超卖")
        elif rsi.signal == RSISignal.OVERBOUGHT:
            parts.append("RSI超买")

        # 成交量
        if volume.is_volume_breakout:
            parts.append("成交放量")

        # 综合建议
        signal_desc = {
            BuySignal.STRONG_BUY: "强烈建议买入",
            BuySignal.BUY: "建议买入",
            BuySignal.WEAK_BUY: "可考虑轻仓买入",
            BuySignal.HOLD: "建议观望",
            BuySignal.WEAK_SELL: "可考虑减仓",
            BuySignal.SELL: "建议卖出",
            BuySignal.STRONG_SELL: "强烈建议卖出",
        }
        parts.append(f"综合评分{score}分，{signal_desc.get(signal, '观望')}")

        return "，".join(parts) + "。"
