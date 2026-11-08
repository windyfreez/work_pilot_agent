# WorkPilot Agent 路线图

分阶段开发，每个阶段独立可验收。

## 阶段 0：项目初始化 ✅

- [x] Git 仓库、目录骨架、Python 虚拟环境。
- [x] 依赖管理（venv + pip + pyproject.toml）与测试框架（pytest）。
- [x] README / AGENTS / architecture / roadmap 文档。
- [x] `.env.example`、`.gitignore`、敏感信息防护。
- [x] 冒烟测试（包导入 + 版本一致性）。

## 阶段 2+3（合并，已完成）✅：文档工具 + 模型客户端 + Agent

- [x] `PathResolver`：授权目录 + 路径解析与越界校验。
- [x] `list_files` / `read_document` / `create_document`（仅 txt/md 文本）。
- [x] Pydantic 工具参数模型（`ListFilesInput` 等）。
- [x] 模型客户端封装（OpenAI 兼容协议，`langchain-openai`）。
- [x] 工具注册到 LangChain `create_agent`（tool-calling 循环）。
- [x] 完整循环 + 异常捕获（`ToolErrorMiddleware`）+ 调用次数限制（`ToolCallLimitMiddleware`）+ 超时（模型请求 + `AgentRunner` 整体超时）。
- [x] 单元测试：路径越界 / 工具异常与边界 / Agent 多步循环、异常捕获、次数限制、超时（假模型，不连真模型）。
- [x] 真实闭环验证：反射式假模型证明「模型发起工具调用 → 程序真实读写文件 → 模型基于真实结果作答」，而非脚本硬编码回答。

**验收**：`pytest` 全绿（40 passed，1 skipped）。依赖：langchain、langchain-core、langchain-openai、pydantic、pydantic-settings。

## 阶段 1（顺延）：API 骨架

- FastAPI 应用骨架、健康检查接口。
- 任务请求 / 响应 schema 初版。

**依赖**：fastapi、uvicorn。

## 阶段 4（已完成）✅：LangGraph 可控工作流

- [x] 统一 `TaskState`（TypedDict）+ `PlanStep` / `Plan` / `VerificationResult`。
- [x] LangGraph 节点：规划（LLM 结构化输出）→ 执行（确定性工具调用）→ 验证 → 结束。
- [x] 最大步骤数（`task_max_steps`）、重试次数（`task_max_retries`）、任务超时（`task_timeout_seconds`）。
- [x] checkpoint 持久化（`langgraph-checkpoint-sqlite`）。
- [x] 写文件幂等（原子写 + 内容相同 no-op）。
- [x] 覆盖写人工确认（`interrupt` + `Command(resume)`）。

**验收**：`pytest` 全绿。依赖新增：langgraph、langgraph-checkpoint-sqlite。

## 阶段 5（已完成）✅：RAG 知识库

- [x] 文档导入与格式解析（txt / md / pdf / docx / xlsx）。
- [x] 文本清洗与分块（自实现，无额外依赖）。
- [x] 向量化写 Chroma（OpenAI 兼容 embedding）+ 来源 / 文件名 / 分块号元数据。
- [x] 语义检索 Top-K + 相关度阈值（无相关资料检测）。
- [x] 检索封装为 LangChain 工具。
- [x] 带来源引用回答 + 无资料兜底（「知识库中没有找到足够依据」）。
- [x] 可重复评测集（`eval/`：问题 / 标准答案 / 预期引用 + recall@k / 引用 / 关键词指标）。

**验收**：`pytest` 全绿（72 passed，1 skipped）。依赖新增：chromadb、langchain-chroma、pypdf、python-docx、openpyxl（dev：reportlab）。

## 阶段 6：执行日志与结果验证

- 结构化执行日志（任务 ID、步骤、耗时）；结果验证器已部分实现（`workflow/verify.py`）。

## 阶段 7：Vue 3 前端

- 前端工程与后端 API 对接。

## 未解决问题

- 文档格式：已支持 txt/md/pdf/docx/xlsx；复杂排版提取精度待增强。
- LLM 供应商：采用 OpenAI 兼容协议，具体供应商 / 模型名经 `.env` 配置；真实调用需人工提供密钥验收。
- langsmith 弃用告警（第三方，测试运行输出 13 条 `asyncio.iscoroutinefunction` 弃用告警）。
- 任务超时语义：当前按单次 `run`/`resume` 调用计时，不含人工确认的等待时间（人工确认跨进程恢复依赖 SQLite checkpoint）。
- RAG 检索阈值：默认不过滤，「无相关资料」检测需按 embedding 标定 `rag_score_threshold`（评测脚本可用 `--score-threshold`）。
