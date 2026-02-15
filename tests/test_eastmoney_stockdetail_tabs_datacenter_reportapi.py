import pytest

from app.datasources.eastmoney import EastMoneyClient


class _DummyResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _DummyHttp:
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None):
        params = params or {}
        self.calls.append((url, params))

        # reportapi：研报/评级
        if url == "https://reportapi.eastmoney.com/report/list":
            return _DummyResp(
                {
                    "hits": 2,
                    "size": 2,
                    "data": [
                        {
                            "title": "研报A",
                            "publishDate": "2026-02-01 00:00:00.000",
                            "orgSName": "机构A",
                            "author": "分析师A",
                            "emRatingName": "买入",
                            "indvAimPriceT": "12.34",
                            "encodeUrl": "https://example.com/a",
                        },
                        {
                            "title": "研报B",
                            "publishDate": "2026-01-15 00:00:00.000",
                            "orgName": "机构B(全称)",
                            "author": ["分析师B1", "分析师B2"],
                            "sRatingName": "增持",
                            "indvAimPriceL": 10.0,
                            "encodeUrl": "https://example.com/b",
                        },
                    ],
                    "TotalPage": 1,
                    "pageNo": 1,
                    "currentYear": 2026,
                }
            )

        # datacenter：股东人数/十大股东/分红/财务报表
        if url == "https://datacenter-web.eastmoney.com/api/data/v1/get":
            report = params.get("reportName")

            if report == "RPT_F10_EH_HOLDERNUM":
                return _DummyResp(
                    {
                        "result": {
                            "data": [
                                {
                                    "END_DATE": "2025-09-30 00:00:00",
                                    "HOLDER_TOTAL_NUM": 119099,
                                    "TOTAL_NUM_RATIO": 2.5752,
                                    "AVG_HOLD_AMT": 3132862.3679,
                                }
                            ]
                        }
                    }
                )

            if report in {"RPT_F10_EH_FREEHOLDERS", "RPT_F10_EH_HOLDERS"}:
                return _DummyResp(
                    {
                        "result": {
                            "data": [
                                {
                                    "HOLDER_NAME": "股东A",
                                    "HOLD_NUM": 100,
                                    "HOLD_RATIO": 1.23,
                                    "HOLD_NUM_CHANGE": "不变",
                                    "HOLD_RATIO_CHANGE": "-0.01",
                                    "HOLDER_TYPE": "其它",
                                    "END_DATE": "2025-09-30 00:00:00",
                                }
                            ]
                        }
                    }
                )

            if report == "RPT_SHAREBONUS_DET":
                return _DummyResp(
                    {
                        "result": {
                            "data": [
                                {
                                    "REPORT_DATE": "2024-12-31 00:00:00",
                                    "IMPL_PLAN_PROFILE": "10派4.10元",
                                    "EX_DIVIDEND_DATE": "2025-07-16 00:00:00",
                                    "EQUITY_RECORD_DATE": "2025-07-15 00:00:00",
                                    "ASSIGN_PROGRESS": "实施分配",
                                    "BONUS_IT_RATIO": None,
                                    "IT_RATIO": None,
                                    "PRETAX_BONUS_RMB": 4.1,
                                }
                            ]
                        }
                    }
                )

            if report == "RPT_LICO_FN_CPD":
                return _DummyResp(
                    {
                        "result": {
                            "data": [
                                {
                                    "REPORTDATE": "2025-09-30 00:00:00",
                                    "TOTAL_OPERATE_INCOME": 123.0,
                                    "PARENT_NETPROFIT": 45.0,
                                    "BASIC_EPS": 1.23,
                                    "BPS": 10.0,
                                    "XSMLL": 33.0,
                                    "YSTZ": 5.0,
                                    "SJLTZ": 6.0,
                                    "WEIGHTAVG_ROE": 7.0,
                                }
                            ]
                        }
                    }
                )

            if report == "RPT_DMSK_FN_BALANCE":
                return _DummyResp(
                    {
                        "result": {
                            "data": [
                                {
                                    "REPORT_DATE": "2025-09-30 00:00:00",
                                    "TOTAL_ASSETS": 1000.0,
                                    "TOTAL_LIABILITIES": 600.0,
                                    "TOTAL_EQUITY": 400.0,
                                }
                            ]
                        }
                    }
                )

        raise AssertionError(f"Unexpected url: {url} params={params}")

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_eastmoney_research_reports_uses_reportapi_and_parses():
    em = EastMoneyClient()
    em.client = _DummyHttp()

    reports = await em.get_stock_research_reports("sh600000", limit=2)
    assert len(reports) == 2
    assert reports[0]["title"] == "研报A"
    assert reports[0]["publish_date"] == "2026-02-01"
    assert reports[0]["org_name"] == "机构A"
    assert reports[0]["author"] == "分析师A"
    assert reports[0]["rating"] == "买入"
    assert reports[0]["target_price"] == pytest.approx(12.34)

    # reportapi 调用参数必须包含 beginTime/endTime/qType
    (url, params) = em.client.calls[0]
    assert url == "https://reportapi.eastmoney.com/report/list"
    assert params.get("code") == "600000"
    assert params.get("beginTime")
    assert params.get("endTime")
    assert params.get("qType") == 0


@pytest.mark.asyncio
async def test_eastmoney_rating_summary_uses_reportapi_and_aggregates():
    em = EastMoneyClient()
    em.client = _DummyHttp()

    summary = await em.get_stock_rating_summary("sh600000", limit=50)
    assert summary["stock_code"] == "sh600000"
    assert summary["rating_count"] == 2
    assert summary["ratings"]["买入"] == 1
    assert summary["ratings"]["增持"] == 1
    assert summary["target_price_count"] == 2
    assert summary["consensus_target_price"] == pytest.approx((12.34 + 10.0) / 2.0, abs=1e-6)
    assert summary["max_target_price"] == pytest.approx(12.34)
    assert summary["min_target_price"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_eastmoney_shareholders_top_holders_dividend_financial_use_eq_filter_and_sort():
    em = EastMoneyClient()
    dummy = _DummyHttp()
    em.client = dummy

    # 1) 股东人数：RPT_F10_EH_HOLDERNUM + 等号过滤（禁止 like）
    shareholders = await em.get_shareholder_count("sh600000")
    assert shareholders and shareholders[0]["end_date"] == "2025-09-30"
    assert shareholders[0]["holder_num"] == 119099
    assert shareholders[0]["holder_num_change_pct"] == pytest.approx(2.5752)
    assert isinstance(shareholders[0]["avg_hold_amount"], float)

    # 2) 十大股东：等号过滤（禁止 like）
    holders = await em.get_top_holders("sh600000", holder_type="float")
    assert holders and holders[0]["holder_name"] == "股东A"
    assert holders[0]["hold_num"] == 100
    assert holders[0]["hold_ratio"] == pytest.approx(1.23)
    # "不变" 需要归一为 0，避免前端把字符串当数字
    assert holders[0]["change"] == 0

    # 3) 分红：IMPL_PLAN_PROFILE 优先
    dividend = await em.get_dividend_history("sh600000")
    assert dividend and dividend[0]["plan"] == "10派4.10元"

    # 4) 财务：利润表 REPORTDATE 排序列存在，且 report_date 从 REPORTDATE 映射
    fin = await em.get_financial_report("sh600000")
    assert fin["income"] and fin["income"][0]["report_date"] == "2025-09-30"
    assert fin["balance"] and fin["balance"][0]["report_date"] == "2025-09-30"

    # 断言调用参数：filter 不应包含 like
    dc_calls = [(u, p) for (u, p) in dummy.calls if u == "https://datacenter-web.eastmoney.com/api/data/v1/get"]
    assert dc_calls, "expected datacenter calls"
    for _, p in dc_calls:
        flt = str(p.get("filter", ""))
        assert "like" not in flt.lower()
        assert 'SECUCODE="600000.SH"' in flt

    # 断言利润表使用 REPORTDATE
    income_call = next(p for (u, p) in dc_calls if p.get("reportName") == "RPT_LICO_FN_CPD")
    assert income_call.get("sortColumns") == "REPORTDATE"

