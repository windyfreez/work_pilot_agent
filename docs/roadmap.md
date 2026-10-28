# WorkPilot Agent 路线图

分阶段开发，每个阶段独立可验收；**当前只执行阶段 0**。

## 阶段 0：项目初始化（当前）✅

- [x] Git 仓库、目录骨架、Python 虚拟环境。
- [x] 依赖管理（venv + pip + pyproject.toml）与测试框架（pytest）。
- [x] README / AGENTS / architecture / roadmap 文档。
- [x] `.env.example`、`.gitignore`、敏感信息防护。
- [x] 冒烟测试（包导入 + 版本一致性）。

**验收**：`pytest` 全绿，`git status` 无敏感文件，文档齐全。

## 阶段 1：API 骨架与配置

- FastAPI 应用骨架、健康检查接口。
- Pydantic `Settings`：从 `.env` 加载配置，启动即校验。
- 任务请求 / 响应 schema 初版。

**依赖**：fastapi、uvicorn、pydantic、pydantic-settings、python-dotenv（按需）。
**风险**：CPython 3.14 对 pydantic-core 的 wheel 支持（需验证，必要时固定 3.12/3.13）。

## 阶段 2：文档工具与路径安全

- `PathResolver`：授权目录 + 路径解析与越界校验。
- 文档读写工具（Markdown / 纯文本起步）。
- 单元测试覆盖路径越界场景。

**依赖**：无强制（或按需引入解析库）。

## 阶段 3：LLM 接入与工具调用

- LangChain 模型封装（选定供应商与模型）。
- 工具注册与调用（绑定阶段 2 的文档工具）。
- 密钥经 `.env` 注入，日志脱敏。

**依赖**：langchain、langchain-core、对应 provider 包。
**风险**：LangChain 对 Python 3.14 的兼容性。

## 阶段 4：LangGraph 工作流编排

- 有状态任务图：读取 → 处理 → 生成 → 校验。
- 状态持久化与重放。

**依赖**：langgraph。

## 阶段 5：RAG 知识库

- Chroma 本地向量库、文档切分与嵌入、检索。
- RAG 问答接口。

**依赖**：chromadb、embedding provider。

## 阶段 6：执行日志与结果验证

- 结构化执行日志（含任务 ID、步骤、耗时）。
- 结果验证器（存在性 / 格式 / 非空等）。

## 阶段 7：Vue 3 前端

- 前端工程与后端 API 对接。

## 未解决问题（跨阶段）

- Python 3.14 兼容性（阶段 1 前置验证）。
- LLM 供应商与模型选型（阶段 3 前确定）。
- 文档格式解析库选型（阶段 2 确定）。
