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

**验收**：`pytest` 全绿（33 passed，1 skipped）。依赖：langchain、langchain-core、langchain-openai、pydantic、pydantic-settings。

## 阶段 1（顺延）：API 骨架

- FastAPI 应用骨架、健康检查接口。
- 任务请求 / 响应 schema 初版。

**依赖**：fastapi、uvicorn。

## 阶段 4：LangGraph 工作流编排

- 显式状态图：读取 → 处理 → 生成 → 校验；状态持久化与重放。

**依赖**：langgraph（已随 langchain 1.x 安装）。

## 阶段 5：RAG 知识库

- Chroma 本地向量库、文档切分 / 嵌入 / 检索、RAG 问答接口。

**依赖**：chromadb、embedding provider。

## 阶段 6：执行日志与结果验证

- 结构化执行日志（任务 ID、步骤、耗时）+ 结果验证器（存在性 / 格式 / 非空）。

## 阶段 7：Vue 3 前端

- 前端工程与后端 API 对接。

## 未解决问题

- 文档格式：仍仅 txt/md；PDF / Word / Excel 解析库选型未定。
- LLM 供应商：采用 OpenAI 兼容协议，具体供应商 / 模型名经 `.env` 配置；真实调用需人工提供密钥验收。
- langsmith 弃用告警（第三方，测试运行输出 13 条 `asyncio.iscoroutinefunction` 弃用告警）。
