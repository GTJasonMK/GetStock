from app.services.technical_service import TechnicalService, RSISignal


def test_rsi_flat_price_is_neutral():
    service = TechnicalService()
    prices = [10.0] * 100

    result = service.calculate_rsi(prices)

    assert result.rsi_6 == 50
    assert result.rsi_12 == 50
    assert result.rsi_24 == 50
    assert result.signal == RSISignal.NEUTRAL


def test_rsi_all_up_is_overbought():
    service = TechnicalService()
    prices = [float(i) for i in range(1, 101)]

    result = service.calculate_rsi(prices)

    assert result.rsi_6 == 100
    assert result.signal == RSISignal.OVERBOUGHT


def test_rsi_all_down_is_oversold():
    service = TechnicalService()
    prices = [float(i) for i in range(100, 0, -1)]

    result = service.calculate_rsi(prices)

    assert result.rsi_6 == 0
    assert result.signal == RSISignal.OVERSOLD

