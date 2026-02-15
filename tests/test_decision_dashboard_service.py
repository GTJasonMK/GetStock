from datetime import datetime

from app.schemas.decision import ChecklistStatusEnum
from app.schemas.technical import (
    BuySignalEnum,
    MACDResponse,
    MACDSignalEnum,
    RSIResponse,
    RSISignalEnum,
    SupportResistanceResponse,
    TechnicalAnalysisResponse,
    TrendAnalysisResponse,
    TrendStatusEnum,
    VolumeAnalysisResponse,
)
from app.services.decision_service import DecisionService


def _make_ta(**overrides):
    base = TechnicalAnalysisResponse(
        stock_code="sh600519",
        name="贵州茅台",
        current_price=1800.0,
        change_percent=1.23,
        trend=TrendAnalysisResponse(
            status=TrendStatusEnum.UP,
            ma_5=1780.0,
            ma_10=1760.0,
            ma_20=1720.0,
            ma_60=1600.0,
            price_position="above_all",
            ma_alignment="bullish",
            bias_5=+1.12,
            bias_10=+2.34,
        ),
        macd=MACDResponse(
            dif=1.23,
            dea=1.11,
            macd=0.24,
            signal=MACDSignalEnum.GOLDEN_CROSS,
            dif_history=[],
            dea_history=[],
            macd_history=[],
        ),
        rsi=RSIResponse(
            rsi_6=55.0,
            rsi_12=52.0,
            rsi_24=49.0,
            signal=RSISignalEnum.NEUTRAL,
        ),
        volume=VolumeAnalysisResponse(
            current_volume=100_000,
            avg_volume_5=80_000.0,
            avg_volume_10=90_000.0,
            volume_ratio=1.25,
            is_volume_breakout=True,
            volume_trend="increasing",
        ),
        support_resistance=SupportResistanceResponse(
            support_1=1750.0,
            support_2=1700.0,
            resistance_1=1850.0,
            resistance_2=1900.0,
            current_price=1800.0,
            distance_to_support=2.00,
            distance_to_resistance=2.50,
        ),
        buy_signal=BuySignalEnum.BUY,
        score=75,
        score_details={"trend": 25, "bias": 18},
        analysis_time=datetime(2026, 2, 7, 12, 0, 0),
        summary="上涨趋势，均线多头排列，MACD金叉。",
    )
    return base.model_copy(update=overrides)


def test_build_dashboard_points_and_checklist_happy_path():
    ta = _make_ta()
    dashboard = DecisionService._build_dashboard(ta)

    assert dashboard.stock_code == "sh600519"
    assert dashboard.buy_signal == BuySignalEnum.BUY
    assert dashboard.points.ideal_buy == 1780.0
    assert dashboard.points.sniper_buy == 1750.0
    assert dashboard.points.stop_loss == 1700.0
    assert dashboard.points.target_1 == 1850.0
    assert dashboard.points.target_2 == 1900.0

    by_key = {i.key: i for i in dashboard.checklist}
    assert by_key["ma_alignment"].status == ChecklistStatusEnum.PASS
    assert by_key["bias"].status == ChecklistStatusEnum.PASS
    assert by_key["macd"].status == ChecklistStatusEnum.PASS
    assert by_key["rsi"].status == ChecklistStatusEnum.PASS
    assert by_key["volume"].status == ChecklistStatusEnum.PASS
    assert by_key["position"].status == ChecklistStatusEnum.PASS


def test_build_dashboard_bias_too_large_marks_fail_and_adds_risk():
    ta = _make_ta(trend=_make_ta().trend.model_copy(update={"bias_5": 9.1}))
    dashboard = DecisionService._build_dashboard(ta)

    bias_item = next(i for i in dashboard.checklist if i.key == "bias")
    assert bias_item.status == ChecklistStatusEnum.FAIL
    assert any("乖离率过大" in r for r in dashboard.risks)

