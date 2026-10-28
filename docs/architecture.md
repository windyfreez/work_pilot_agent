# WorkPilot Agent 架构设计

> 状态：**目标架构（规划）**。阶段 0 未实现任何运行时组件，本文用于对齐后续各阶段的实现边界。

## 1. 总览

WorkPilot 是一条可审计的执行链：

```
用户请求 → API 层(FastAPI) → 编排(LangGraph) → 工具(文档读写) + RAG(Chroma) → 结果校验 → 执行日志
```

核心诉求：任务可编排、过程可审计、文件操作安全、结果可验证。

## 2. 分层架构

| 层 | 职责 | 技术 | 阶段 |
|----|------|------|------|
| 接口层 | HTTP 接口、参数校验、会话管理 | FastAPI + Pydantic | 1 |
| 编排层 | 有状态任务编排、重试、分支 | LangGraph | 4 |
| 智能层 | 模型接入、工具调用、RAG 检索 | LangChain + Chroma | 3 / 5 |
| 工具层 | 文档读写、路径校验、授权目录 | 自研 + 解析库 | 2 |
| 观测层 | 执行日志、结果验证 | 结构化日志 + 校验器 | 6 |
| 存储层 | 向量库、会话/任务状态 | Chroma + 本地存储 | 5 / 6 |

## 3. 目录结构（规划）

```
src/workpilot/
├── api/          # FastAPI 路由与依赖注入
├── schemas/      # Pydantic 数据模型（请求/响应/状态）
├── config/       # 环境变量加载与校验（.env）
├── agent/        # LangChain 工具调用与模型接入
├── workflow/     # LangGraph 状态图与节点
├── tools/        # 文档读写工具 + 路径安全校验
├── rag/          # Chroma 向量库、切分与检索
├── logging/      # 结构化执行日志
└── verify/       # 结果验证器
```

## 4. 关键设计决策

- **src 布局**：`src/workpilot`，避免隐式导入，测试与发布更清晰。
- **配置经 Pydantic**：环境变量 → `Settings` 模型，启动即校验，缺密钥即失败。
- **路径安全前置**：文件工具统一走 `PathResolver`，校验 `resolve()` 后的路径落在 `WORKPILOT_ALLOWED_DIRS` 内。
- **状态显式化**：LangGraph `State` 由 Pydantic 描述，便于持久化与重放。
- **RAG 本地化**：Chroma 持久化目录不入库（`chroma/` 已忽略）。

## 5. 数据流（示例场景）

「读取报告 → 提炼要点 → 生成摘要文档」

1. API 接收任务 → Pydantic 校验参数。
2. LangGraph 建图：`read` → `summarize(LLM)` → `write` → `verify`。
3. `read` 工具经路径校验读取授权目录内文件。
4. `summarize` 调用 LLM（含可选 RAG 上下文）。
5. `write` 工具写入授权目录。
6. `verify` 校验产物（存在性、格式、非空），写执行日志。

## 6. 安全边界

- 秘密只经 `.env`，不入代码 / 日志 / 提交。
- 文件操作严格限权 + 路径校验。
- 日志脱敏：不记录密钥与用户文件内容。

## 7. 阶段 0 交付 vs 未交付

- **已交付**：Git 仓库、venv、`pyproject.toml`、`.gitignore`、`.env.example`、README/AGENTS/架构/路线图、冒烟测试。
- **未交付**：上述所有运行时组件（按 roadmap 逐阶段实现）。
