# Browser 爬虫模块
"""
基于 Playwright 的浏览器爬虫
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from contextlib import asynccontextmanager

try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserPool:
    """浏览器连接池"""

    def __init__(self, pool_size: int = 3, headless: bool = True):
        self.pool_size = pool_size
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: List[BrowserContext] = []
        self._available: asyncio.Queue = asyncio.Queue()
        self._initialized = False

    async def init(self):
        """初始化浏览器池"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright未安装，请运行: pip install playwright && playwright install chromium")

        if self._initialized:
            return

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        # 创建多个上下文
        for _ in range(self.pool_size):
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self._contexts.append(context)
            await self._available.put(context)

        self._initialized = True

    async def close(self):
        """关闭浏览器池"""
        if not self._initialized:
            return

        for context in self._contexts:
            await context.close()

        if self._browser:
            await self._browser.close()

        if self._playwright:
            await self._playwright.stop()

        self._initialized = False

    @asynccontextmanager
    async def get_context(self):
        """获取一个浏览器上下文"""
        if not self._initialized:
            await self.init()

        context = await self._available.get()
        try:
            yield context
        finally:
            await self._available.put(context)

    @asynccontextmanager
    async def get_page(self):
        """获取一个页面"""
        async with self.get_context() as context:
            page = await context.new_page()
            try:
                yield page
            finally:
                await page.close()


class Crawler:
    """网页爬虫"""

    def __init__(self, pool: Optional[BrowserPool] = None):
        self.pool = pool or BrowserPool()

    async def init(self):
        """初始化"""
        await self.pool.init()

    async def close(self):
        """关闭"""
        await self.pool.close()

    async def get_html(
        self,
        url: str,
        timeout: int = 30000,
        wait_selector: Optional[str] = None,
        wait_time: int = 0
    ) -> str:
        """
        获取页面HTML
        url: 目标URL
        timeout: 超时时间(毫秒)
        wait_selector: 等待某个元素出现
        wait_time: 额外等待时间(毫秒)
        """
        async with self.pool.get_page() as page:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=timeout)

            if wait_time > 0:
                await asyncio.sleep(wait_time / 1000)

            return await page.content()

    async def get_html_with_actions(
        self,
        url: str,
        actions: List[Dict[str, Any]],
        timeout: int = 30000
    ) -> str:
        """
        执行一系列操作后获取HTML
        actions: [
            {"type": "click", "selector": "#btn"},
            {"type": "fill", "selector": "#input", "value": "text"},
            {"type": "wait", "time": 1000},
            {"type": "scroll", "y": 500},
        ]
        """
        async with self.pool.get_page() as page:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            for action in actions:
                action_type = action.get("type")

                if action_type == "click":
                    await page.click(action["selector"])
                elif action_type == "fill":
                    await page.fill(action["selector"], action["value"])
                elif action_type == "wait":
                    await asyncio.sleep(action.get("time", 1000) / 1000)
                elif action_type == "scroll":
                    await page.evaluate(f"window.scrollTo(0, {action.get('y', 500)})")
                elif action_type == "wait_selector":
                    await page.wait_for_selector(action["selector"], timeout=timeout)

            return await page.content()

    async def evaluate(
        self,
        url: str,
        script: str,
        timeout: int = 30000
    ) -> Any:
        """
        在页面中执行JavaScript并返回结果
        """
        async with self.pool.get_page() as page:
            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return await page.evaluate(script)

    async def screenshot(
        self,
        url: str,
        path: str,
        full_page: bool = False,
        timeout: int = 30000
    ) -> str:
        """截图"""
        async with self.pool.get_page() as page:
            await page.goto(url, timeout=timeout, wait_until="networkidle")
            await page.screenshot(path=path, full_page=full_page)
            return path


# 全局爬虫实例
_crawler: Optional[Crawler] = None


async def get_crawler() -> Crawler:
    """获取全局爬虫实例"""
    global _crawler
    if _crawler is None:
        _crawler = Crawler()
        await _crawler.init()
    return _crawler


async def close_crawler():
    """关闭全局爬虫实例"""
    global _crawler
    if _crawler:
        await _crawler.close()
        _crawler = None
