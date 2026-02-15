# 决策仪表盘服务
"""
决策仪表盘：基于现有技术分析结果生成结构化“买卖点位 + 检查清单 + 风险点”。

说明：
- 默认不依赖 LLM，保持可解释与稳定。
- 复用 TechnicalService 的输出，面向 Web 看板展示。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.technical import _get_klines
from app.schemas.decision import (
    ChecklistStatusEnum,
    DecisionChecklistItem,
    DecisionDashboardResponse,
    DecisionPoints,
)
from app.schemas.technical import (
    BuySignalEnum,
    MACDSignalEnum,
    RSISignalEnum,
    TechnicalAnalysisResponse,
    TrendAnalysisResponse,
    MACDResponse,
    RSIResponse,
    VolumeAnalysisResponse,
    SupportResistanceResponse,
    TrendStatusEnum,
)
from app.services.technical_service import TechnicalService, TechnicalAnalysisResult


class DecisionService:
    """决策仪表盘服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_dashboard(
        self,
        stock_code: str,
        *,
        days: int = 120,
        include_technical: bool = True,
    ) -> DecisionDashboardResponse:
        """
        生成单只股票的决策仪表盘（规则版）。

        days: 用于技术分析的日K条数（>=60）
        include_technical: 是否附带技术分析明细（前端可直接展示/复用）
        """
        count = int(days)
        if count < 60:
            raise ValueError("days 需 >= 60")

        klines, stock_name, normalized_code = await _get_klines(stock_code, self.db, count=count)

        service = TechnicalService()
        result = await service.analyze(normalized_code, klines, stock_name)
        technical = self._map_technical_result(result)

        dashboard = self._build_dashboard(technical)
        if include_technical:
            dashboard.technical = technical
        return dashboard

    @staticmethod
    def _map_technical_result(result: TechnicalAnalysisResult) -> TechnicalAnalysisResponse:
        """将 TechnicalService 的结果映射为对外的 Pydantic schema。"""
        return TechnicalAnalysisResponse(
            stock_code=result.code,
            name=result.name,
            current_price=result.current_price,
            change_percent=result.change_percent,
            trend=TrendAnalysisResponse(
                status=TrendStatusEnum(result.trend.status.value),
                ma_5=result.trend.ma_5,
                ma_10=result.trend.ma_10,
                ma_20=result.trend.ma_20,
                ma_60=result.trend.ma_60,
                price_position=result.trend.price_position,
                ma_alignment=result.trend.ma_alignment,
                bias_5=result.trend.bias_5,
                bias_10=result.trend.bias_10,
            ),
            macd=MACDResponse(
                dif=result.macd.dif,
                dea=result.macd.dea,
                macd=result.macd.macd,
                signal=MACDSignalEnum(result.macd.signal.value),
                dif_history=result.macd.dif_history,
                dea_history=result.macd.dea_history,
                macd_history=result.macd.macd_history,
            ),
            rsi=RSIResponse(
                rsi_6=result.rsi.rsi_6,
                rsi_12=result.rsi.rsi_12,
                rsi_24=result.rsi.rsi_24,
                signal=RSISignalEnum(result.rsi.signal.value),
            ),
            volume=VolumeAnalysisResponse(
                current_volume=result.volume.current_volume,
                avg_volume_5=result.volume.avg_volume_5,
                avg_volume_10=result.volume.avg_volume_10,
                volume_ratio=result.volume.volume_ratio,
                is_volume_breakout=result.volume.is_volume_breakout,
                volume_trend=result.volume.volume_trend,
            ),
            support_resistance=SupportResistanceResponse(
                support_1=result.support_resistance.support_1,
                support_2=result.support_resistance.support_2,
                resistance_1=result.support_resistance.resistance_1,
                resistance_2=result.support_resistance.resistance_2,
                current_price=result.support_resistance.current_price,
                distance_to_support=result.support_resistance.distance_to_support,
                distance_to_resistance=result.support_resistance.distance_to_resistance,
            ),
            buy_signal=BuySignalEnum(result.buy_signal.value),
            score=result.score,
            score_details=result.score_details,
            analysis_time=result.analysis_time,
            summary=result.summary,
        )

    @staticmethod
    def _round_price(v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        try:
            return round(float(v), 2)
        except Exception:
            return None

    @classmethod
    def _build_dashboard(cls, ta: TechnicalAnalysisResponse) -> DecisionDashboardResponse:
        sr = ta.support_resistance
        trend = ta.trend

        ideal_buy = cls._round_price(trend.ma_5 if trend.ma_5 > 0 else None)
        sniper_buy = cls._round_price(sr.support_1 if sr.support_1 > 0 else None)

        # 止损位：优先取（支撑2 / MA20）中的更低者，确保 < sniper_buy
        stop_candidates: List[float] = []
        if sr.support_2 and sr.support_2 > 0:
            stop_candidates.append(sr.support_2)
        if trend.ma_20 and trend.ma_20 > 0:
            stop_candidates.append(trend.ma_20)
        stop_loss = min(stop_candidates) if stop_candidates else None
        if sniper_buy and stop_loss is not None and stop_loss >= sniper_buy:
            stop_loss = sniper_buy * 0.97
        stop_loss = cls._round_price(stop_loss)

        target_1 = cls._round_price(sr.resistance_1 if sr.resistance_1 > 0 else None)
        target_2 = cls._round_price(sr.resistance_2 if sr.resistance_2 > 0 else None)

        points = DecisionPoints(
            ideal_buy=ideal_buy,
            sniper_buy=sniper_buy,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
        )

        checklist: List[DecisionChecklistItem] = []
        risks: List[str] = []

        # 1) 均线趋势（多头/空头/混乱）
        if trend.ma_alignment == "bullish":
            checklist.append(DecisionChecklistItem(
                key="ma_alignment",
                label="趋势/均线",
                status=ChecklistStatusEnum.PASS,
                message="均线多头排列（MA5>MA10>MA20>MA60）",
            ))
        elif trend.ma_alignment == "bearish":
            checklist.append(DecisionChecklistItem(
                key="ma_alignment",
                label="趋势/均线",
                status=ChecklistStatusEnum.FAIL,
                message="均线空头排列（MA5<MA10<MA20<MA60）",
            ))
            risks.append("均线空头排列：不宜做多，优先控仓/等待趋势反转。")
        else:
            checklist.append(DecisionChecklistItem(
                key="ma_alignment",
                label="趋势/均线",
                status=ChecklistStatusEnum.WARN,
                message="均线排列混乱：等待方向更清晰",
            ))

        # 2) 乖离率（绝不追高：>5% 直接警戒）
        bias5 = float(trend.bias_5 or 0.0)
        abs_bias5 = abs(bias5)
        if abs_bias5 <= 5:
            checklist.append(DecisionChecklistItem(
                key="bias",
                label="乖离安全",
                status=ChecklistStatusEnum.PASS,
                message=f"乖离率(MA5) {bias5:+.2f}%（安全）",
            ))
        elif abs_bias5 <= 8:
            checklist.append(DecisionChecklistItem(
                key="bias",
                label="乖离安全",
                status=ChecklistStatusEnum.WARN,
                message=f"乖离率(MA5) {bias5:+.2f}%（偏大，谨慎追高）",
            ))
            risks.append("乖离率偏大：避免追高，优先等待回踩 MA5/支撑位。")
        else:
            checklist.append(DecisionChecklistItem(
                key="bias",
                label="乖离安全",
                status=ChecklistStatusEnum.FAIL,
                message=f"乖离率(MA5) {bias5:+.2f}%（过大，禁止追高）",
            ))
            risks.append("乖离率过大（>8%）：禁止追高，等待回调后再评估。")

        # 3) MACD
        macd_sig = ta.macd.signal
        if macd_sig in (MACDSignalEnum.GOLDEN_CROSS, MACDSignalEnum.BULLISH):
            checklist.append(DecisionChecklistItem(
                key="macd",
                label="MACD",
                status=ChecklistStatusEnum.PASS,
                message=f"MACD {macd_sig.value}（偏多）",
            ))
        elif macd_sig == MACDSignalEnum.NEUTRAL:
            checklist.append(DecisionChecklistItem(
                key="macd",
                label="MACD",
                status=ChecklistStatusEnum.WARN,
                message="MACD 中性：等待进一步确认",
            ))
        else:
            checklist.append(DecisionChecklistItem(
                key="macd",
                label="MACD",
                status=ChecklistStatusEnum.FAIL,
                message=f"MACD {macd_sig.value}（偏空）",
            ))
            risks.append("MACD 偏空：短线反弹可能受限，避免重仓逆势。")

        # 4) RSI
        rsi_sig = ta.rsi.signal
        if rsi_sig == RSISignalEnum.OVERBOUGHT:
            checklist.append(DecisionChecklistItem(
                key="rsi",
                label="RSI",
                status=ChecklistStatusEnum.WARN,
                message="RSI 超买：警惕回调风险",
            ))
            risks.append("RSI 超买：更适合等待回踩/分批止盈。")
        elif rsi_sig == RSISignalEnum.OVERSOLD:
            checklist.append(DecisionChecklistItem(
                key="rsi",
                label="RSI",
                status=ChecklistStatusEnum.PASS,
                message="RSI 超卖：关注企稳信号",
            ))
        else:
            checklist.append(DecisionChecklistItem(
                key="rsi",
                label="RSI",
                status=ChecklistStatusEnum.PASS,
                message="RSI 中性：无明显超买/超卖",
            ))

        # 5) 量能配合（量比/放量突破）
        vr = float(ta.volume.volume_ratio or 0.0)
        if ta.volume.is_volume_breakout or vr >= 1.5:
            checklist.append(DecisionChecklistItem(
                key="volume",
                label="量能",
                status=ChecklistStatusEnum.PASS,
                message=f"量比 {vr:.2f}（量能配合）",
            ))
        elif vr >= 1.0:
            checklist.append(DecisionChecklistItem(
                key="volume",
                label="量能",
                status=ChecklistStatusEnum.WARN,
                message=f"量比 {vr:.2f}（一般）",
            ))
        else:
            checklist.append(DecisionChecklistItem(
                key="volume",
                label="量能",
                status=ChecklistStatusEnum.WARN,
                message=f"量比 {vr:.2f}（偏弱，注意持续性）",
            ))

        # 6) 位置（距支撑/阻力）
        ds = float(sr.distance_to_support or 0.0)
        dr = float(sr.distance_to_resistance or 0.0)
        if ds <= 2:
            checklist.append(DecisionChecklistItem(
                key="position",
                label="位置",
                status=ChecklistStatusEnum.PASS,
                message=f"距支撑 {ds:.2f}%（更像回踩位）",
            ))
        elif ds <= 5:
            checklist.append(DecisionChecklistItem(
                key="position",
                label="位置",
                status=ChecklistStatusEnum.WARN,
                message=f"距支撑 {ds:.2f}%（偏离，谨慎追高）",
            ))
        else:
            checklist.append(DecisionChecklistItem(
                key="position",
                label="位置",
                status=ChecklistStatusEnum.FAIL,
                message=f"距支撑 {ds:.2f}%（偏离较大）",
            ))
            risks.append("当前价格偏离支撑位较远：追高性价比低，等待回踩更优。")

        if dr <= 1:
            risks.append("接近阻力位：上方空间可能受限，注意压力与回撤。")

        # 综合风险：根据 buy_signal 提醒
        if ta.buy_signal in (BuySignalEnum.SELL, BuySignalEnum.STRONG_SELL):
            risks.append("技术面信号偏空：更适合防守与纪律止损/减仓。")
        elif ta.buy_signal in (BuySignalEnum.WEAK_SELL,):
            risks.append("技术面偏弱：优先控仓，等待信号改善。")

        return DecisionDashboardResponse(
            stock_code=ta.stock_code,
            stock_name=ta.name or ta.stock_code,
            buy_signal=ta.buy_signal,
            score=int(ta.score),
            summary=str(ta.summary or ""),
            points=points,
            checklist=checklist,
            risks=risks,
            generated_at=datetime.now(),
            data_sources=["technical"],
            technical=None,
        )

