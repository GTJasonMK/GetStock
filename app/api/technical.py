# 技术分析API
"""
技术分析相关的API端点
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.common import Response
from app.schemas.technical import (
    TechnicalAnalysisResponse,
    MACDResponse,
    RSIResponse,
    TrendAnalysisResponse,
    VolumeAnalysisResponse,
    SupportResistanceResponse,
    BatchTechnicalRequest,
    BatchTechnicalResponse,
    MACDSignalEnum,
    RSISignalEnum,
    TrendStatusEnum,
    BuySignalEnum,
)
from app.services.technical_service import (
    TechnicalService,
    MACDSignal,
    RSISignal,
    TrendStatus,
    BuySignal,
)
from app.datasources.manager import get_datasource_manager
from app.utils.cache import cache, CacheTTL, make_cache_key
from app.utils.helpers import normalize_stock_code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/technical", tags=["技术分析"])


def _convert_macd_signal(signal: MACDSignal) -> MACDSignalEnum:
    """转换MACD信号枚举"""
    mapping = {
        MACDSignal.GOLDEN_CROSS: MACDSignalEnum.GOLDEN_CROSS,
        MACDSignal.DEATH_CROSS: MACDSignalEnum.DEATH_CROSS,
        MACDSignal.BULLISH: MACDSignalEnum.BULLISH,
        MACDSignal.BEARISH: MACDSignalEnum.BEARISH,
        MACDSignal.NEUTRAL: MACDSignalEnum.NEUTRAL,
    }
    return mapping.get(signal, MACDSignalEnum.NEUTRAL)


def _convert_rsi_signal(signal: RSISignal) -> RSISignalEnum:
    """转换RSI信号枚举"""
    mapping = {
        RSISignal.OVERSOLD: RSISignalEnum.OVERSOLD,
        RSISignal.OVERBOUGHT: RSISignalEnum.OVERBOUGHT,
        RSISignal.NEUTRAL: RSISignalEnum.NEUTRAL,
    }
    return mapping.get(signal, RSISignalEnum.NEUTRAL)


def _convert_trend_status(status: TrendStatus) -> TrendStatusEnum:
    """转换趋势状态枚举"""
    mapping = {
        TrendStatus.STRONG_UP: TrendStatusEnum.STRONG_UP,
        TrendStatus.UP: TrendStatusEnum.UP,
        TrendStatus.WEAK_UP: TrendStatusEnum.WEAK_UP,
        TrendStatus.CONSOLIDATION: TrendStatusEnum.CONSOLIDATION,
        TrendStatus.WEAK_DOWN: TrendStatusEnum.WEAK_DOWN,
        TrendStatus.DOWN: TrendStatusEnum.DOWN,
        TrendStatus.STRONG_DOWN: TrendStatusEnum.STRONG_DOWN,
    }
    return mapping.get(status, TrendStatusEnum.CONSOLIDATION)


def _convert_buy_signal(signal: BuySignal) -> BuySignalEnum:
    """转换买卖信号枚举"""
    mapping = {
        BuySignal.STRONG_BUY: BuySignalEnum.STRONG_BUY,
        BuySignal.BUY: BuySignalEnum.BUY,
        BuySignal.WEAK_BUY: BuySignalEnum.WEAK_BUY,
        BuySignal.HOLD: BuySignalEnum.HOLD,
        BuySignal.WEAK_SELL: BuySignalEnum.WEAK_SELL,
        BuySignal.SELL: BuySignalEnum.SELL,
        BuySignal.STRONG_SELL: BuySignalEnum.STRONG_SELL,
    }
    return mapping.get(signal, BuySignalEnum.HOLD)


def _validate_kline(k: dict) -> bool:
    """
    校验单条 K 线数据的有效性
    返回 True 表示数据有效，False 表示无效应过滤
    """
    try:
        close = k.get("close")
        high = k.get("high")
        low = k.get("low")
        volume = k.get("volume")

        # close 必须存在且大于 0
        if close is None or float(close) <= 0:
            return False

        # high/low 必须存在且合法（high >= low > 0）
        if high is None or low is None:
            return False
        high_val = float(high)
        low_val = float(low)
        if high_val <= 0 or low_val <= 0 or high_val < low_val:
            return False

        # volume 必须存在且 >= 0
        if volume is None or int(volume) < 0:
            return False

        return True
    except (ValueError, TypeError):
        return False


def _safe_float(value, default: float = 0.0) -> float:
    """安全地将值转换为 float，处理 None 和无效值"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """安全地将值转换为 int，处理 None 和无效值"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


async def _get_klines(code: str, db: AsyncSession, count: int = 100) -> tuple[list, str, str]:
    """获取K线数据（带缓存和数据校验）"""
    normalized_code = normalize_stock_code(code)
    if not normalized_code:
        raise HTTPException(status_code=400, detail="股票代码不能为空")

    # 检查缓存
    cache_key = make_cache_key("klines", normalized_code, count)
    cached_value = await cache.get(cache_key)
    if cached_value is not None:
        logger.debug(f"K线数据缓存命中: {normalized_code}")
        klines, stock_name = cached_value
        return klines, stock_name, normalized_code

    manager = get_datasource_manager()
    # 使用数据库配置初始化数据源管理器，避免首次调用未加载配置导致配置永远不生效
    await manager.initialize(db)

    try:
        kline_response = await manager.get_kline(normalized_code, period="day", count=count)
        # 转换为字典列表并校验数据
        klines = []
        invalid_count = 0
        for k in kline_response.data:
            kline_dict = {
                "date": k.date,
                "open": k.open,
                "close": k.close,
                "high": k.high,
                "low": k.low,
                "volume": k.volume,
            }
            # 校验数据有效性
            if _validate_kline(kline_dict):
                klines.append(kline_dict)
            else:
                invalid_count += 1

        if invalid_count > 0:
            logger.warning(f"K线数据校验: {code} 过滤了 {invalid_count} 条无效数据")

        if not klines:
            raise HTTPException(status_code=500, detail=f"获取K线数据失败: 无有效数据")

        result = (klines, kline_response.stock_name)
        # 存入缓存
        await cache.set(cache_key, result, CacheTTL.KLINE)
        return klines, kline_response.stock_name, normalized_code
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取K线数据失败: input={code}, normalized={normalized_code}, {e}")
        raise HTTPException(status_code=500, detail=f"获取K线数据失败: {e}")


@router.get("/{code}", response_model=Response[TechnicalAnalysisResponse])
async def get_technical_analysis(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取股票完整技术分析

    - **code**: 股票代码 (如 sh600519, sz000001)
    """
    klines, stock_name, normalized_code = await _get_klines(code, db, count=100)

    if len(klines) < 60:
        raise HTTPException(status_code=400, detail=f"K线数据不足，需要至少60条，当前: {len(klines)}")

    service = TechnicalService()
    result = await service.analyze(normalized_code, klines, stock_name)

    return Response(data=TechnicalAnalysisResponse(
        stock_code=result.code,
        name=result.name,
        current_price=result.current_price,
        change_percent=result.change_percent,
        trend=TrendAnalysisResponse(
            status=_convert_trend_status(result.trend.status),
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
            signal=_convert_macd_signal(result.macd.signal),
            dif_history=result.macd.dif_history,
            dea_history=result.macd.dea_history,
            macd_history=result.macd.macd_history,
        ),
        rsi=RSIResponse(
            rsi_6=result.rsi.rsi_6,
            rsi_12=result.rsi.rsi_12,
            rsi_24=result.rsi.rsi_24,
            signal=_convert_rsi_signal(result.rsi.signal),
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
        buy_signal=_convert_buy_signal(result.buy_signal),
        score=result.score,
        score_details=result.score_details,
        analysis_time=result.analysis_time,
        summary=result.summary,
    ))


@router.post("/batch", response_model=Response[BatchTechnicalResponse])
async def batch_technical_analysis(
    request: BatchTechnicalRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批量技术分析

    - **codes**: 股票代码列表 (最多20个)
    """
    results = []
    failed = []

    service = TechnicalService()

    for code in request.codes:
        try:
            klines, stock_name, normalized_code = await _get_klines(code, db, count=100)

            if len(klines) < 60:
                failed.append(code)
                continue

            result = await service.analyze(normalized_code, klines, stock_name)

            results.append(TechnicalAnalysisResponse(
                stock_code=result.code,
                name=result.name,
                current_price=result.current_price,
                change_percent=result.change_percent,
                trend=TrendAnalysisResponse(
                    status=_convert_trend_status(result.trend.status),
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
                    signal=_convert_macd_signal(result.macd.signal),
                    dif_history=result.macd.dif_history,
                    dea_history=result.macd.dea_history,
                    macd_history=result.macd.macd_history,
                ),
                rsi=RSIResponse(
                    rsi_6=result.rsi.rsi_6,
                    rsi_12=result.rsi.rsi_12,
                    rsi_24=result.rsi.rsi_24,
                    signal=_convert_rsi_signal(result.rsi.signal),
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
                buy_signal=_convert_buy_signal(result.buy_signal),
                score=result.score,
                score_details=result.score_details,
                analysis_time=result.analysis_time,
                summary=result.summary,
            ))
        except Exception as e:
            logger.error(f"技术分析失败: {code}, {e}")
            failed.append(code)

    return Response(data=BatchTechnicalResponse(results=results, failed=failed))


@router.get("/{code}/macd", response_model=Response[MACDResponse])
async def get_macd(code: str, db: AsyncSession = Depends(get_db)):
    """获取MACD指标"""
    klines, _, _ = await _get_klines(code, db, count=100)

    if len(klines) < 35:
        raise HTTPException(status_code=400, detail="K线数据不足")

    service = TechnicalService()
    closes = [_safe_float(k.get("close")) for k in klines]
    result = service.calculate_macd(closes)

    return Response(data=MACDResponse(
        dif=result.dif,
        dea=result.dea,
        macd=result.macd,
        signal=_convert_macd_signal(result.signal),
        dif_history=result.dif_history,
        dea_history=result.dea_history,
        macd_history=result.macd_history,
    ))


@router.get("/{code}/rsi", response_model=Response[RSIResponse])
async def get_rsi(code: str, db: AsyncSession = Depends(get_db)):
    """获取RSI指标"""
    klines, _, _ = await _get_klines(code, db, count=50)

    if len(klines) < 30:
        raise HTTPException(status_code=400, detail="K线数据不足")

    service = TechnicalService()
    closes = [_safe_float(k.get("close")) for k in klines]
    result = service.calculate_rsi(closes)

    return Response(data=RSIResponse(
        rsi_6=result.rsi_6,
        rsi_12=result.rsi_12,
        rsi_24=result.rsi_24,
        signal=_convert_rsi_signal(result.signal),
    ))


@router.get("/{code}/trend", response_model=Response[TrendAnalysisResponse])
async def get_trend(code: str, db: AsyncSession = Depends(get_db)):
    """获取趋势分析"""
    klines, _, _ = await _get_klines(code, db, count=100)

    if len(klines) < 60:
        raise HTTPException(status_code=400, detail="K线数据不足")

    service = TechnicalService()
    closes = [_safe_float(k.get("close")) for k in klines]
    current_price = closes[-1]
    result = service.analyze_trend(closes, current_price)

    return Response(data=TrendAnalysisResponse(
        status=_convert_trend_status(result.status),
        ma_5=result.ma_5,
        ma_10=result.ma_10,
        ma_20=result.ma_20,
        ma_60=result.ma_60,
        price_position=result.price_position,
        ma_alignment=result.ma_alignment,
        bias_5=result.bias_5,
        bias_10=result.bias_10,
    ))


@router.get("/{code}/volume", response_model=Response[VolumeAnalysisResponse])
async def get_volume_analysis(code: str, db: AsyncSession = Depends(get_db)):
    """获取成交量分析"""
    klines, _, _ = await _get_klines(code, db, count=30)

    if len(klines) < 10:
        raise HTTPException(status_code=400, detail="K线数据不足")

    service = TechnicalService()
    volumes = [_safe_int(k.get("volume")) for k in klines]
    result = service.analyze_volume(volumes)

    return Response(data=VolumeAnalysisResponse(
        current_volume=result.current_volume,
        avg_volume_5=result.avg_volume_5,
        avg_volume_10=result.avg_volume_10,
        volume_ratio=result.volume_ratio,
        is_volume_breakout=result.is_volume_breakout,
        volume_trend=result.volume_trend,
    ))


@router.get("/{code}/support-resistance", response_model=Response[SupportResistanceResponse])
async def get_support_resistance(code: str, db: AsyncSession = Depends(get_db)):
    """获取支撑阻力位"""
    klines, _, _ = await _get_klines(code, db, count=30)

    if len(klines) < 20:
        raise HTTPException(status_code=400, detail="K线数据不足")

    service = TechnicalService()
    highs = [_safe_float(k.get("high")) for k in klines]
    lows = [_safe_float(k.get("low")) for k in klines]
    current_price = _safe_float(klines[-1].get("close"))

    result = service.calculate_support_resistance(highs, lows, current_price)

    return Response(data=SupportResistanceResponse(
        support_1=result.support_1,
        support_2=result.support_2,
        resistance_1=result.resistance_1,
        resistance_2=result.resistance_2,
        current_price=result.current_price,
        distance_to_support=result.distance_to_support,
        distance_to_resistance=result.distance_to_resistance,
    ))
