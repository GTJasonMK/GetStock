# Go-Stock Python 后端

基于 FastAPI 的股票分析后端服务，提供股票数据查询、AI分析、资讯获取等功能。

## 功能特性

- 股票数据：实时行情、K线数据、自选股管理
- 市场资讯：财联社电报、新浪财经、全球指数
- AI分析：LLM对话、股票诊断、简化数据分析（Simple Agent，数据→结论）
- 配置管理：系统设置、AI配置、导入导出
- 分组管理：自选股分组
- 基金数据：基金查询、关注
- 市场数据：行业排名、资金流向、龙虎榜、宏观经济

## AI 分析说明

- 默认推荐：`POST /api/v1/ai/simple`（固定数据收集 → 输出结论，不依赖复杂编排）
- 可选保留：`POST /api/v1/ai/agent`（高级编排能力，非必须）
- 详见 `docs/agent.md`

## 技术栈

- **Web框架**: FastAPI (异步)
- **ORM**: SQLAlchemy 2.0 (异步支持)
- **数据库**: SQLite (aiosqlite)
- **HTTP客户端**: httpx
- **数据验证**: Pydantic v2
- **定时任务**: APScheduler
- **浏览器自动化**: Playwright

## 安装

```bash
cd recon

# 创建虚拟环境 (推荐)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器 (可选，用于爬虫功能)
playwright install chromium
```

## 配置

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

配置项说明：
- `DEBUG`: 调试模式
- `HOST`: 监听地址
- `PORT`: 监听端口
- `DATABASE_URL`: 数据库连接URL
- `LOG_LEVEL`: 日志级别
- `MARKET_TIMEZONE`: 市场时区（默认 `Asia/Shanghai`）
- `ENABLE_SCHEDULER`: 是否启用定时任务（默认 true）
- `SCHEDULER_LOCK_PATH`: scheduler 进程锁文件路径（多 worker 选主，默认 `./data/scheduler.lock`）

## 运行

```bash
# 开发模式 (热重载)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# 生产模式
# 注意：多 worker 部署时，scheduler 会通过文件锁选主，仅 leader 进程执行定时任务，避免重复执行
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

## API文档

启动后访问：
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## 项目结构

```
recon/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI入口
│   ├── config.py            # 配置管理
│   ├── database.py          # 数据库连接
│   │
│   ├── models/              # SQLAlchemy模型
│   │   ├── settings.py      # Settings, AIConfig
│   │   ├── stock.py         # FollowedStock, Group
│   │   ├── market.py        # StockInfo, StockBasic
│   │   ├── news.py          # Telegraph, Tags
│   │   ├── ai.py            # AIResponseResult
│   │   ├── fund.py          # FollowedFund, FundBasic
│   │   └── market_data.py   # LongTigerRankData, BKDict
│   │
│   ├── schemas/             # Pydantic模型
│   │   ├── settings.py
│   │   ├── stock.py
│   │   ├── news.py
│   │   ├── market.py
│   │   ├── ai.py
│   │   ├── fund.py
│   │   └── common.py
│   │
│   ├── api/                 # API路由
│   │   ├── router.py        # 主路由
│   │   ├── settings.py      # 配置API
│   │   ├── stock.py         # 股票API
│   │   ├── group.py         # 分组API
│   │   ├── news.py          # 资讯API
│   │   ├── market.py        # 市场API
│   │   ├── ai.py            # AI API
│   │   └── fund.py          # 基金API
│   │
│   ├── services/            # 业务逻辑
│   │   ├── stock_service.py
│   │   ├── news_service.py
│   │   ├── market_service.py
│   │   ├── fund_service.py
│   │   └── ai_service.py
│   │
│   ├── datasources/         # 外部数据源
│   │   ├── sina.py          # 新浪财经
│   │   ├── tencent.py       # 腾讯财经
│   │   ├── eastmoney.py     # 东方财富
│   │   ├── cls.py           # 财联社
│   │   └── fund.py          # 天天基金
│   │
│   ├── llm/                 # LLM集成
│   │   ├── client.py        # 统一LLM客户端
│   │   └── agent.py         # ReACT Agent
│   │
│   ├── tasks/               # 定时任务
│   │   └── scheduler.py
│   │
│   └── utils/               # 工具函数
│       └── helpers.py
│
├── tests/                   # 测试
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

## API路由

```
/api/v1/
├── /settings              # 配置管理
│   ├── GET    /           # 获取配置
│   ├── PUT    /           # 更新配置
│   ├── GET    /ai-configs # AI配置列表
│   ├── POST   /ai-configs # 创建AI配置
│   ├── PUT    /ai-configs/{id}  # 更新AI配置
│   ├── DELETE /ai-configs/{id}  # 删除AI配置
│   ├── POST   /export     # 导出配置
│   └── POST   /import     # 导入配置
│
├── /stock                 # 股票数据
│   ├── GET    /list       # 搜索股票
│   ├── GET    /follow     # 自选股列表
│   ├── POST   /follow     # 添加自选
│   ├── PUT    /follow/{code}    # 更新自选
│   ├── DELETE /follow/{code}    # 移除自选
│   ├── GET    /realtime   # 实时行情
│   ├── GET    /{code}/kline     # K线数据
│   └── GET    /{code}/minute    # 分钟数据
│
├── /group                 # 分组管理
│   ├── GET    /           # 分组列表
│   ├── POST   /           # 创建分组
│   ├── PUT    /{id}       # 更新分组
│   ├── DELETE /{id}       # 删除分组
│   ├── POST   /{id}/stock       # 添加股票
│   └── DELETE /{id}/stock/{code}# 移除股票
│
├── /news                  # 资讯
│   ├── GET    /latest     # 最新资讯
│   ├── GET    /telegraph  # 财联社电报
│   └── GET    /global-indexes   # 全球指数
│
├── /market                # 市场数据
│   ├── GET    /industry-rank    # 行业排名
│   ├── GET    /money-flow       # 资金流向
│   ├── GET    /long-tiger       # 龙虎榜
│   ├── GET    /economic         # 宏观经济
│   └── GET    /sector/{code}/stocks  # 板块成分股
│
├── /ai                    # AI分析
│   ├── POST   /chat       # AI对话
│   ├── POST   /chat/stream      # 流式对话 (SSE)
│   ├── POST   /analyze    # 股票分析
│   ├── POST   /simple     # 简化版分析（固定数据收集→结论）
│   ├── POST   /simple/stream    # 简化版分析流式 (SSE)
│   ├── POST   /agent      # Agent对话（支持 mode=chat/agent/do/think/auto）
│   ├── POST   /agent/stream     # Agent流式 (SSE)
│   ├── GET    /sessions   # 会话列表
│   ├── GET    /sessions/{session_id} # 会话详情（含消息）
│   ├── DELETE /sessions/{session_id} # 删除会话（含消息）
│   ├── GET    /history    # 历史记录
│   └── DELETE /history/{id}     # 删除记录
│
├── /agent/knowledge       # Agent 知识库（对齐 LearningSelfAgent 分层检索）
│   ├── POST   /retrieve   # 分层检索（图谱→领域→技能→方案→工具文档）
│   ├── GET    /domains    # 领域列表
│   ├── GET    /skills     # 技能列表
│   ├── POST   /skills     # 创建技能
│   ├── PUT    /skills/{id}# 更新技能
│   ├── DELETE /skills/{id}# 禁用技能
│   ├── GET    /solutions  # 方案列表
│   ├── POST   /solutions  # 创建方案
│   ├── PUT    /solutions/{id} # 更新方案
│   ├── DELETE /solutions/{id} # 禁用方案
│   ├── GET    /tools      # 工具文档列表
│   ├── GET    /graph      # 图谱节点列表
│   ├── POST   /graph      # 创建图谱节点
│   ├── PUT    /graph/{id} # 更新图谱节点
│   ├── DELETE /graph/{id} # 禁用图谱节点
│   └── GET    /runs       # AgentRun 列表（含 evaluation/score）
│
└── /fund                  # 基金数据
    ├── GET    /list       # 基金搜索
    ├── GET    /follow     # 关注列表
    ├── POST   /follow     # 关注基金
    ├── PUT    /follow/{code}    # 更新关注
    ├── DELETE /follow/{code}    # 取消关注
    ├── GET    /{code}           # 基金详情
    └── GET    /{code}/net-value # 净值历史
```

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_settings.py

# 显示详细输出
pytest -v
```

## 与前端对接

前端需要将原有的 Wails IPC 调用改为 HTTP API 调用：

```javascript
// 原来的 Wails 调用
const result = await GetStockRealtime(codes);

// 改为 fetch 调用
const response = await fetch(`http://localhost:8001/api/v1/stock/realtime?codes=${codes}`);
const result = await response.json();
```

流式响应使用 SSE：

```javascript
const eventSource = new EventSource(`http://localhost:8001/api/v1/ai/chat/stream`);
eventSource.onmessage = (event) => {
    if (event.data === '[DONE]') {
        eventSource.close();
        return;
    }
    const data = JSON.parse(event.data);
    // 处理流式数据
};
```

## 许可证

MIT
