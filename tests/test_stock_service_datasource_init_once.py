import asyncio

import pytest

from app.services.stock_service import StockService


@pytest.mark.asyncio
async def test_get_datasource_manager_initializes_once_under_concurrency(monkeypatch):
    import app.datasources.manager as manager_module

    class FakeManager:
        def __init__(self):
            self.init_calls = 0

        async def initialize(self, db=None):
            self.init_calls += 1
            await asyncio.sleep(0.01)

    fake_manager = FakeManager()
    monkeypatch.setattr(manager_module, "get_datasource_manager", lambda: fake_manager)

    service = StockService(db=object())
    results = await asyncio.gather(*[service._get_datasource_manager() for _ in range(10)])

    assert all(item is fake_manager for item in results)
    assert fake_manager.init_calls == 1
