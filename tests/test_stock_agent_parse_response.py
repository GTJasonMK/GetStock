from unittest.mock import MagicMock

from app.llm.agent import StockAgent
from app.models.settings import AIConfig


def _make_agent() -> StockAgent:
    config = AIConfig(
        name="test",
        enabled=True,
        base_url="https://example.com/v1",
        api_key="test-key",
        model_name="gpt-test",
        max_tokens=16,
        temperature=0.0,
        timeout=3,
        http_proxy="",
        http_proxy_enabled=False,
    )
    return StockAgent(config, MagicMock())


def test_parse_response_inline_action_input_json():
    agent = _make_agent()
    content = """Thought: 查询一下实时行情
Action: query_stock_price
Action Input: {"stock_codes": "sh600000,sz000001"}
"""

    thought, action, action_input, final_answer = agent._parse_response(content)
    assert "实时" in thought
    assert action == "query_stock_price"
    assert action_input == {"stock_codes": "sh600000,sz000001"}
    assert final_answer == ""


def test_parse_response_action_input_code_fence_multiline():
    agent = _make_agent()
    content = """Thought: 获取日K
Action: query_stock_kline
Action Input:
```json
{"stock_code": "sh600000", "days": 30}
```
"""

    _, action, action_input, _ = agent._parse_response(content)
    assert action == "query_stock_kline"
    assert action_input == {"stock_code": "sh600000", "days": 30}


def test_parse_response_supports_chinese_section_headers():
    agent = _make_agent()
    content = """思考：先看市场概览
行动：query_market_overview
行动输入：{}
最终回答：今天整体偏强，建议关注资金流向与板块轮动。
"""

    thought, action, action_input, final_answer = agent._parse_response(content)
    assert "市场概览" in thought
    assert action == "query_market_overview"
    assert action_input == {}
    assert "建议关注" in final_answer


def test_parse_response_cleans_tool_name_and_extracts_embedded_json_object():
    agent = _make_agent()
    content = """Thought: 取北向资金
Action: `query_north_flow`
Action Input: 参数如下：{"days": 10}
"""

    _, action, action_input, _ = agent._parse_response(content)
    assert action == "query_north_flow"
    assert action_input == {"days": 10}
