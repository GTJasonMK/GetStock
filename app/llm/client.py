# LLM Client
"""
统一LLM客户端，支持OpenAI兼容格式
"""

import asyncio
import random
from typing import List, AsyncGenerator, Optional

import httpx

from app.models.settings import AIConfig
from app.schemas.ai import ChatMessage, ChatResponse, StreamChunk


class LLMClient:
    """统一LLM客户端"""

    def __init__(self, config: AIConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.api_key = config.api_key
        self.model = config.model_name
        self.max_tokens = config.max_tokens
        self.temperature = config.temperature
        self.timeout = config.timeout

        # 配置代理
        proxies = None
        if config.http_proxy_enabled and config.http_proxy:
            proxies = {"all://": config.http_proxy}

        self.client = httpx.AsyncClient(
            timeout=float(self.timeout),
            proxies=proxies,
        )

    async def close(self):
        await self.client.aclose()

    def _validate_config(self) -> None:
        """基础配置校验，避免把明显配置错误当成“网络错误”"""
        if not self.base_url or not str(self.base_url).startswith(("http://", "https://")):
            raise ValueError("AI base_url 未正确配置（应为 http/https 开头）")
        if not self.api_key or str(self.api_key).strip() in {"", "your_api_key"} or str(self.api_key).startswith("your_"):
            raise ValueError("AI api_key 未配置或为占位符")
        if not self.model or not str(self.model).strip():
            raise ValueError("AI model_name 未配置")

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(self, messages: List[ChatMessage]) -> List[dict]:
        """构建消息格式"""
        return [{"role": m.role, "content": m.content} for m in messages]

    @staticmethod
    def _join_url(base_url: str, path: str) -> str:
        """拼接 base_url 与 path，避免出现 /v1/v1 这类重复路径"""
        base = (base_url or "").rstrip("/")
        p = (path or "").strip()
        if not p:
            return base
        if not p.startswith("/"):
            p = "/" + p

        # 常见配置会把 base_url 写成 .../v1，此时再拼 /v1/... 会变成 /v1/v1/...
        if base.endswith("/v1") and p.startswith("/v1/"):
            p = p[len("/v1") :]

        return base + p

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        """是否为可重试的 HTTP 状态码"""
        return status_code in {408, 409, 429, 500, 502, 503, 504}

    async def _sleep_backoff(self, attempt: int, base_delay: float = 1.0, max_delay: float = 20.0) -> None:
        """指数退避（带抖动），对齐 daily_stock_analysis 的稳定性策略"""
        if attempt <= 0:
            return
        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
        # 抖动避免同一时间段并发重试造成雪崩
        delay = delay * (0.7 + random.random() * 0.6)
        await asyncio.sleep(delay)

    async def chat(self, messages: List[ChatMessage]) -> ChatResponse:
        """非流式对话"""
        self._validate_config()
        url = self._join_url(self.base_url, "/v1/chat/completions")

        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }

        # 简单重试：网络抖动/限流/5xx 时退避重试，提高“可用性”
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                if attempt:
                    await self._sleep_backoff(attempt)

                response = await self.client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                data = response.json()
                break
            except httpx.HTTPStatusError as e:
                last_error = e
                status = getattr(e.response, "status_code", 0) or 0
                if not self._is_retryable_status(int(status)) or attempt >= 2:
                    raise
                continue
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
                last_error = e
                if attempt >= 2:
                    raise
                continue
        else:  # pragma: no cover
            raise last_error or RuntimeError("LLM 请求失败")

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return ChatResponse(
            response=message.get("content", ""),
            model_name=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    async def chat_stream(self, messages: List[ChatMessage]) -> AsyncGenerator[StreamChunk, None]:
        """流式对话"""
        self._validate_config()
        url = self._join_url(self.base_url, "/v1/chat/completions")

        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
        }

        # 流式场景只能在“开始读取前”做重试；一旦进入流读取，中断后无法安全重放。
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                if attempt:
                    await self._sleep_backoff(attempt)

                async with self.client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=self._get_headers(),
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        data_str = line[6:]  # 去掉 "data: " 前缀
                        if data_str == "[DONE]":
                            yield StreamChunk(content="", done=True, model_name=self.model)
                            return

                        import json

                        try:
                            data = json.loads(data_str)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")

                            if content:
                                yield StreamChunk(
                                    content=content,
                                    done=False,
                                    model_name=self.model,
                                )
                        except json.JSONDecodeError:
                            continue
                return
            except httpx.HTTPStatusError as e:
                last_error = e
                status = getattr(e.response, "status_code", 0) or 0
                if not self._is_retryable_status(int(status)) or attempt >= 2:
                    raise
                continue
            except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
                last_error = e
                if attempt >= 2:
                    raise
                continue

        raise last_error or RuntimeError("LLM 流式请求失败")


class OpenAIClient(LLMClient):
    """OpenAI客户端"""
    pass


class DeepSeekClient(LLMClient):
    """DeepSeek客户端"""
    pass


class AnthropicClient(LLMClient):
    """Anthropic客户端 (Claude)"""

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    def _build_messages(self, messages: List[ChatMessage]) -> tuple:
        """构建消息格式，返回(system, messages)"""
        system = ""
        user_messages = []

        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                user_messages.append({"role": m.role, "content": m.content})

        return system, user_messages

    async def chat(self, messages: List[ChatMessage]) -> ChatResponse:
        """非流式对话"""
        self._validate_config()
        url = self._join_url(self.base_url, "/v1/messages")

        system, user_messages = self._build_messages(messages)

        payload = {
            "model": self.model,
            "messages": user_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system:
            payload["system"] = system

        response = await self.client.post(
            url,
            json=payload,
            headers=self._get_headers(),
        )
        response.raise_for_status()
        data = response.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = data.get("usage", {})

        return ChatResponse(
            response=content,
            model_name=self.model,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        )

    async def chat_stream(self, messages: List[ChatMessage]) -> AsyncGenerator[StreamChunk, None]:
        """流式对话 - Anthropic格式"""
        self._validate_config()
        url = self._join_url(self.base_url, "/v1/messages")

        system, user_messages = self._build_messages(messages)

        payload = {
            "model": self.model,
            "messages": user_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system

        async with self.client.stream(
            "POST",
            url,
            json=payload,
            headers=self._get_headers(),
        ) as response:
            response.raise_for_status()

            import json

            async for line in response.aiter_lines():
                if not line:
                    continue

                # Anthropic SSE格式: event: xxx\ndata: {...}
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    continue

                if not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                    event_type = data.get("type", "")

                    # 处理content_block_delta事件
                    if event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield StreamChunk(
                                    content=text,
                                    done=False,
                                    model_name=self.model,
                                )

                    # 处理message_stop事件
                    elif event_type == "message_stop":
                        yield StreamChunk(
                            content="",
                            done=True,
                            model_name=self.model,
                        )
                        break

                    # 处理错误事件
                    elif event_type == "error":
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                        raise Exception(f"Anthropic API error: {error_msg}")

                except json.JSONDecodeError:
                    continue
