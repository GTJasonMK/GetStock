# CLS 数据源客户端
"""
财联社数据接口
"""

import json
from typing import List, Any, Dict
from datetime import datetime

import httpx

from app.schemas.news import TelegraphItem, TelegraphResponse, NewsItem


class CLSClient:
    """财联社客户端"""

    # 2026-02-02：cls.cn 原 `/api/*` 返回 404，改为 `/v1/api/*`
    BASE_URL = "https://www.cls.cn/v1/api"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.cls.cn/",
            }
        )

    async def close(self):
        await self.client.aclose()

    async def _get_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """请求并解析 JSON（财联社接口可能返回 HTML/非 JSON）"""
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise Exception(f"财联社API请求失败: HTTP {e.response.status_code}") from e
        except Exception as e:
            raise Exception(f"财联社API请求失败: {e}") from e

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise Exception("财联社API返回非JSON（可能被拦截/接口变更）") from e
        except Exception as e:
            raise Exception(f"财联社API解析JSON失败: {e}") from e

        if not isinstance(data, dict):
            raise Exception("财联社API返回结构异常（非 dict）")

        # 部分情况下会返回 {"errno": 50101, "msg": "小财正在加载中..."} 之类的拦截提示
        errno = data.get("errno")
        if isinstance(errno, int) and errno != 0:
            msg = data.get("msg") or data.get("message") or ""
            raise Exception(f"财联社API返回错误: errno={errno}, msg={msg}")

        return data

    async def get_telegraph(self, page: int = 1, page_size: int = 20) -> TelegraphResponse:
        """获取财联社电报"""
        url = f"{self.BASE_URL}/telegraph/get"
        params = {
            "page": page,
            "page_size": page_size,
            "app": "web",
        }
        data = await self._get_json(url, params)

        items = []
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}

        telegraph_data = payload.get("roll_data") or payload.get("data") or []
        if not isinstance(telegraph_data, list):
            telegraph_data = []

        for item in telegraph_data:
            # 提取标签
            tags = []
            for tag in item.get("subjects", []) or []:
                tags.append(tag.get("name", ""))

            items.append(TelegraphItem(
                telegraph_id=str(item.get("id", "")),
                publish_time=datetime.fromtimestamp(item.get("ctime", 0)),
                title=item.get("title", "") or item.get("brief", ""),
                content=item.get("content", ""),
                source="cls",
                importance=item.get("level", 1),
                tags=tags,
            ))

        total = payload.get("total", len(items))
        has_more = page * page_size < total

        return TelegraphResponse(items=items, total=total, has_more=has_more, source="cls", notice="")

    async def get_news(self, limit: int = 20) -> List[NewsItem]:
        """获取财联社资讯"""
        url = f"{self.BASE_URL}/depth/list"
        params = {
            "type": "stock",
            "page": 1,
            "page_size": limit,
            "app": "web",
        }
        data = await self._get_json(url, params)

        items = []
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}

        rows = payload.get("data") or payload.get("roll_data") or []
        if not isinstance(rows, list):
            rows = []

        for item in rows:
            items.append(NewsItem(
                news_id=str(item.get("id", "")),
                title=item.get("title", ""),
                content=item.get("brief", "") or item.get("content", ""),
                source="cls",
                publish_time=datetime.fromtimestamp(item.get("ctime", 0)),
                url=f"https://www.cls.cn/detail/{item.get('id', '')}",
                image_url=item.get("img", "") or "",
            ))

        return items
