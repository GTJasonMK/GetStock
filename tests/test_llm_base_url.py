import pytest

from app.llm.client import LLMClient, AnthropicClient
from app.models.settings import AIConfig
from app.schemas.ai import ChatMessage


@pytest.mark.asyncio
async def test_llm_client_base_url_with_v1_does_not_duplicate_v1(monkeypatch):
    called = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    async def fake_post(url, json, headers):
        called["url"] = url
        return FakeResponse()

    config = AIConfig(
        name="test",
        enabled=True,
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        model_name="gpt-4",
        max_tokens=16,
        temperature=0.0,
        timeout=3,
        http_proxy="",
        http_proxy_enabled=False,
    )

    client = LLMClient(config)
    monkeypatch.setattr(client.client, "post", fake_post)

    try:
        resp = await client.chat([ChatMessage(role="user", content="hi")])
        assert resp.response == "ok"
        assert called["url"] == "https://api.openai.com/v1/chat/completions"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_anthropic_client_base_url_with_v1_does_not_duplicate_v1(monkeypatch):
    called = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    async def fake_post(url, json, headers):
        called["url"] = url
        return FakeResponse()

    config = AIConfig(
        name="test",
        enabled=True,
        base_url="https://api.anthropic.com/v1",
        api_key="test-key",
        model_name="claude-3",
        max_tokens=16,
        temperature=0.0,
        timeout=3,
        http_proxy="",
        http_proxy_enabled=False,
    )

    client = AnthropicClient(config)
    monkeypatch.setattr(client.client, "post", fake_post)

    try:
        resp = await client.chat([ChatMessage(role="user", content="hi")])
        assert resp.response == "ok"
        assert called["url"] == "https://api.anthropic.com/v1/messages"
    finally:
        await client.close()

