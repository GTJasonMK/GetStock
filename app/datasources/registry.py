# 数据源注册表
"""
集中管理“数据源名称 -> 客户端类”的映射，避免在 DataSourceManager 中堆 if/elif。

设计目标：
- 低耦合：Manager 不直接依赖各数据源模块的实现细节；
- 可扩展：新增数据源只需要在注册表登记（或运行时注册）；
- 便于测试：单测可通过 monkeypatch 替换模块属性，registry 会在运行时 getattr，天然兼容。
"""

from __future__ import annotations

import importlib
from typing import Any, Dict, Tuple, Type


# 约定：source_name 与 datasource_config.source_name 保持一致
DATASOURCE_CLIENT_SPECS: Dict[str, Tuple[str, str]] = {
    "sina": ("app.datasources.sina", "SinaClient"),
    "eastmoney": ("app.datasources.eastmoney", "EastMoneyClient"),
    "tencent": ("app.datasources.tencent", "TencentClient"),
    "tushare": ("app.datasources.tushare", "TushareClient"),
    # 港股/美股 K 线兜底（AkShare）
    "akshare": ("app.datasources.akshare", "AkShareClient"),
    # news/fund sources（当前不在默认优先级中；按需显式指定 sources 调用）
    "cls": ("app.datasources.cls", "CLSClient"),
    "fund": ("app.datasources.fund", "TianTianFundClient"),
}


def register_datasource(source: str, module: str, attr: str) -> None:
    """运行时注册/覆盖某个数据源客户端（便于扩展与测试）。"""
    key = (source or "").strip()
    if not key:
        raise ValueError("source 不能为空")
    if not module or not attr:
        raise ValueError("module/attr 不能为空")
    DATASOURCE_CLIENT_SPECS[key] = (module, attr)


def load_client_class(source: str) -> Type[Any]:
    """按 source 加载客户端类（延迟 import + getattr，兼容 monkeypatch）。"""
    key = (source or "").strip()
    spec = DATASOURCE_CLIENT_SPECS.get(key)
    if not spec:
        raise ValueError(f"未知数据源: {source}")

    module_name, attr_name = spec
    module = importlib.import_module(module_name)
    cls = getattr(module, attr_name, None)
    if cls is None:
        raise RuntimeError(f"数据源客户端不存在: {module_name}.{attr_name}")
    return cls


def list_supported_sources() -> list[str]:
    """列出当前支持的数据源名称。"""
    return sorted(DATASOURCE_CLIENT_SPECS.keys())
