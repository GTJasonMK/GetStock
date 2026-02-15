# Recon Agent 说明（默认简化版 + 可选高级编排）

日期：2026-02-04  
执行者：Codex  
范围：`/mnt/e/code/GetStock/recon`

按你最新需求，本项目**默认只需要“简单数据分析→结论”的 Agent**，因此前端入口已收敛为：

- `对话`：`/api/v1/ai/chat(/stream)`（普通对话）
- `分析(简化版)`：`/api/v1/ai/simple(/stream)`（固定并发拉取数据 → 交给 LLM 输出结论）

同时，为了后续可扩展性，仓库内仍保留了对齐 `LearningSelfAgent/docs/agent` 的“高级编排能力”（mode 路由、分层检索、Plan-ReAct、评估与运行记录等），但**不再作为默认使用路径**。

参考文档（本机路径）：
- `/mnt/e/code/LearningSelfAgent/docs/agent/README.md`
- `/mnt/e/code/LearningSelfAgent/docs/agent/01-core-design.md`
- `/mnt/e/code/LearningSelfAgent/docs/agent/02-execution-stages.md`
- `/mnt/e/code/LearningSelfAgent/docs/agent/03-knowledge-layers.md`

---

## 1. 默认使用：简化版 Agent（✅）

### 1.1 简化版数据流水线

固定并发拉取（容错）：
- 个股：行情/估值/资金/K线(120)/技术分析/筹码/公告/研报/市场概览（尽量取到就用，取不到会记录 missing）
- 无股票上下文：市场概览 +（可选）资讯检索

实现位置：
- `app/services/simple_agent_service.py`
- `app/services/ai_service.py`：`simple_agent_chat()` / `simple_agent_chat_stream()`
- `app/api/ai.py`：`POST /api/v1/ai/simple`、`POST /api/v1/ai/simple/stream`

### 1.2 前端入口

AI 面板默认仅保留“对话/分析”两种模式（不暴露 Plan-ReAct/Think 等高级模式）。

实现位置：
- `frontend/src/components/panels/AIPanel.tsx`
- `frontend/src/lib/api.ts`：`simpleAgentStreamWithMessages()`

---

## 2. 可选能力：高级编排（⚠️ 可不用）

### 2.1 模式路由（chat/do/think/agent/auto）

- `mode=chat`：普通对话（不走工具链）
- `mode=do`：Plan → ReAct（单模型执行）
- `mode=think`：多候选 Plan → 选择 → ReAct（当前为“同模型多视角”，不引入多 Agent 依赖）
- `mode=agent`：兼容旧 ReAct 行为
- `mode=auto`：按问题关键词/股票上下文做轻量路由

实现位置（可选）：
- `app/services/ai_service.py`：`_normalize_agent_mode()`、`_route_mode()`、`agent_chat()`、`agent_chat_stream()`
- `app/llm/agent.py`：`run_do()`、`run_think()`、`run_mode_stream()`

### 2.2 多轮记忆 / 会话持久化

- 后端使用 `AISession/AISessionMessage` 持久化会话与消息
- 前端通过 `session_id`（localStorage）恢复会话
- 当客户端只传本轮消息时，后端会自动拼接最近 N 条历史（`max_context_messages`）

实现位置（可选）：
- `app/models/ai_session.py`
- `app/api/ai.py`：`/api/v1/ai/sessions*`
- `app/services/ai_service.py`：`_get_or_create_session()`、`_get_session_context_messages()`、`_append_session_message()`

### 2.3 分层知识检索（图谱→领域→技能→方案→工具文档）

- 目标：减少“只会对话但拿不到可用信息”的情况，为规划与执行注入稳定上下文
- 默认 seed：domains + core skill + solutions + tool docs（从运行时 `TOOLS` 自动生成）
- 检索结果会拼成 `knowledge_context` 注入 do/think 的 planner/executor

实现位置（可选）：
- `app/models/agent_knowledge.py`（AgentDomain/Skill/Solution/ToolDoc/GraphNode/Run）
- `app/services/agent_knowledge_service.py`：`ensure_seeded()`、`retrieve()`、`format_as_context()`
- `app/api/agent_knowledge.py`：`/api/v1/agent/knowledge/retrieve`

### 2.4 Plan-ReAct（可观测事件流）

- SSE 事件用于前端可视化：`session/plan/step_start/step_done/tool_call/observation/final_answer/error`
- 有利于定位“为什么没数据/为什么没调用工具/在哪一步失败”

实现位置（可选）：
- `app/llm/agent.py`：`run_mode_stream()`
- `app/services/ai_service.py`：`agent_chat_stream()`（负责事件透传 + 首包 session）

### 2.5 执行记录 + 评估（AgentRun）

- 每次 do/think 执行都会写入 `AgentRun`：question/plan/tools/answer/context
- 默认启用**启发式评估**写入 `AgentRun.evaluation/score`（离线可用、测试可跑）
- 可选启用 `enable_llm_evaluation=true` 使用同一模型生成结构化评估 JSON（有额外成本）

实现位置（可选）：
- `app/models/agent_knowledge.py`：`AgentRun`
- `app/services/agent_evaluation_service.py`
- `app/services/ai_service.py`：落库 AgentRun 时写入 evaluation/score
- `app/api/agent_knowledge.py`：`GET /api/v1/agent/knowledge/runs`

---

## 3. 与范式差异（⚠️ / TODO）

- **多 Agent 协作执行**：当前 `think` 是“同模型多候选规划 + 选择 + ReAct”，尚未实现真正多 Agent 分工协作（如 A 写代码/B 写文档/C 验证）。
- **知识沉淀闭环**：目前已具备“运行记录 + 评估 + 知识库 CRUD”，但尚未实现“从高分 run 自动生成 draft → 人工审批 → 入库”的完整工作流。

---

## 4. API 使用说明（最小可用）

### 4.1 简化版 Agent（推荐）

`POST /api/v1/ai/simple` / `POST /api/v1/ai/simple/stream`

说明：
- 你只要问“分析 sh600000/浦发银行...”，后端会自动抓取数据并输出结论。
- 如需减少外部搜索带来的不确定性，可将 `enable_retrieval=false`。

### 4.2 高级 Agent 对话（可选）

`POST /api/v1/ai/agent`

关键请求字段（见 `app/schemas/ai.py`）：
- `mode`: `chat|agent|do|think|auto`
- `session_id`: 可选；用于会话持久化
- `max_context_messages`: 后端拼接历史的上限（默认 20）
- `enable_run_evaluation`: 是否落库评估（默认 true）
- `enable_llm_evaluation`: 是否启用 LLM 评估（默认 false）

### 4.3 高级 Agent（流式 SSE）

`POST /api/v1/ai/agent/stream`

事件 `type`：
- `session`：首包回传 `session_id`
- `plan`：规划 JSON
- `step_start/step_done`：步骤进度
- `tool_call/observation`：工具调用与观测
- `final_answer`：最终答案
- `error`：错误信息（后端会尽量转为可读语义）

### 4.4 知识检索 / 知识维护（CRUD）

检索：
- `POST /api/v1/agent/knowledge/retrieve`

维护：
- `POST/PUT/DELETE /api/v1/agent/knowledge/skills*`
- `POST/PUT/DELETE /api/v1/agent/knowledge/solutions*`
- `POST/PUT/DELETE /api/v1/agent/knowledge/graph*`

---

## 5. 推荐维护流程（贴近文档范式）

1) 用 `do/think` 跑一轮任务 → 在 `/agent/knowledge/runs` 查看 `evaluation/score`
2) 把高质量 run 的“做法”抽象为 `skills/solutions`
3) 把高频坑/约束沉淀为 `graph_nodes`（例如：数据源字段变更、解析失败模式、缓存口径）
4) 需要更强评审时再开启 `enable_llm_evaluation=true`（避免默认成本上升）
