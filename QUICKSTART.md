# Stock Recon - 快速开始

Python FastAPI 后端 + Next.js 前端的股票分析应用

## 快速开始

### 1. 一键安装依赖

```bash
# 方式1: 直接运行
python install.py

# 方式2: Windows 双击
install.bat
```

**安装内容：**
- ✓ 自动检测/安装 uv 包管理器
- ✓ 创建 Python 虚拟环境 (`.venv`)
- ✓ 安装 Python 后端依赖
- ✓ 安装 Next.js 前端依赖
- ✓ (可选) 安装 Playwright 浏览器

### 2. 一键启动服务

```bash
# 方式1: 直接运行
python start.py

# 方式2: Windows 双击
start.bat
```

**启动内容：**
- ✓ FastAPI 后端 - http://localhost:8001
- ✓ Next.js 前端 - http://localhost:3001
- ✓ API 文档 - http://localhost:8001/docs

按 `Ctrl+C` 停止所有服务。

---

## 环境要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.10 | 后端运行环境 |
| Node.js | ≥ 18 | 前端运行环境 |
| npm | - | Node.js 包管理器 |

---

## 目录结构

```
recon/
├── app/                  # Python 后端代码
│   ├── api/             # API 路由
│   ├── models/          # 数据模型
│   ├── services/        # 业务逻辑
│   ├── datasources/     # 数据源客户端
│   └── main.py          # FastAPI 入口
├── frontend/            # Next.js 前端代码
│   ├── src/app/         # App Router
│   └── package.json
├── .venv/              # Python 虚拟环境
├── install.py          # 一键安装脚本
├── install.bat         # Windows 安装脚本
├── start.py            # 一键启动脚本
├── start.bat           # Windows 启动脚本
└── requirements.txt    # Python 依赖
```

---

## 手动操作

如果自动脚本失败，可以手动执行以下步骤：

### 后端

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动后端
uvicorn app.main:app --reload --port 8001
```

### 前端

```bash
cd frontend
npm install
npm run dev -- --port 3001
```

---

## 功能模块

| 模块 | API 端点 | 功能 |
|------|----------|------|
| 股票 | `/api/v1/stock/*` | 实时行情、K线、自选股 |
| 市场 | `/api/v1/market/*` | 行业排名、资金流向、龙虎榜 |
| 资讯 | `/api/v1/news/*` | 财联社电报、全球指数 |
| AI | `/api/v1/ai/*` | 智能分析、对话、摘要 |
| 设置 | `/api/v1/settings/*` | 系统配置、AI 配置 |
| 分组 | `/api/v1/group/*` | 自选股分组管理 |
| 基金 | `/api/v1/fund/*` | 基金搜索、关注 |

---

## 常见问题

### 1. 端口被占用

脚本会自动检测并终止占用端口的进程。如果失败，手动执行：

```bash
# Windows
netstat -ano | findstr :8001
taskkill /F /PID <PID>

# Linux/Mac
lsof -ti:8001 | xargs kill -9
```

默认端口可通过环境变量覆盖：
- 后端：`BACKEND_PORT`（默认 8001）
- 前端：`FRONTEND_PORT`（默认 3001）

### 2. 虚拟环境未激活

确保后端在虚拟环境中运行：
```bash
# 检查是否在虚拟环境中
python -c "import sys; print(sys.prefix)"

# 应该输出虚拟环境路径，如: E:\code\GetStock\recon\.venv
```

### 3. uv 安装失败

手动安装 uv：
```bash
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# Linux/Mac
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 开发

### Agentation 工具栏

前端已集成 Agentation 开发工具栏，启动后在右下角查看（仅开发模式）。

### API 文档

访问 http://localhost:8001/docs 查看自动生成的 Swagger 文档。

---

## 许可

本软件仅供学习和研究使用，不构成投资建议。股市有风险，投资需谨慎。
