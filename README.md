# WorkPilot Agent

一个能够执行办公任务的智能 Agent：支持文档读取与生成、多步骤任务执行、RAG 知识库问答、执行日志与结果验证。

> **当前状态：文档工具 + 模型客户端 + LangChain Agent 已就绪。** 尚未实现 FastAPI API、RAG、MCP 或前端功能。

## 项目目标

- **文档读写**：读取与生成常见办公文档（Markdown / 纯文本起步，后续扩展 PDF / Word / Excel）。
- **多步骤执行**：通过工作流编排完成复合办公任务（如「读取文件 → 分析 → 生成报告」）。
- **RAG 问答**：基于本地向量库（Chroma）进行知识库问答。
- **可审计**：记录执行日志，并对任务结果做校验。

## 功能边界（当前阶段）

已实现（对应 roadmap「阶段 2+3」合并）：

- ✅ 模型客户端封装（OpenAI 兼容协议：OpenAI / DeepSeek / Ollama）。
- ✅ Pydantic 工具参数模型。
- ✅ 三个文件工具：`list_files` / `read_document` / `create_document`（含路径校验与授权目录）。
- ✅ 工具注册到 LangChain Agent（`create_agent` tool-calling 循环）。

尚未实现：

- ⛔ FastAPI API 层、RAG（Chroma）、MCP、执行日志 / 结果验证、Vue 3 前端。

## 技术栈

| 层 | 技术 | 状态 |
|----|------|------|
| 语言 | Python 3.11+（开发环境 3.14.5） | ✅ |
| 模型接入 | LangChain（`ChatOpenAI`，OpenAI 兼容） | ✅ 已实现 |
| 工具调用 | LangChain `create_agent` | ✅ 已实现 |
| 工作流 | LangGraph | 阶段 4（`create_agent` 底层已使用） |
| 校验 | Pydantic + pydantic-settings | ✅ 已实现 |
| API | FastAPI | 阶段 1（顺延） |
| 知识库 | Chroma | 阶段 5 |
| 前端 | Vue 3 | 阶段 7 |

## 目录结构

```
work_pilot_agent/
├── .gitignore
├── .env.example          # 环境变量模板（仅占位符）
├── AGENTS.md             # AI Coding 开发规范
├── README.md
├── pyproject.toml        # 依赖与测试配置（PEP 621）
├── conftest.py           # pytest 沙盒适配（临时目录重定向 + 目录 mode 放宽）
├── docs/
│   ├── architecture.md
│   └── roadmap.md
├── src/workpilot/
│   ├── __init__.py
│   ├── config/           # Settings（pydantic-settings 读 .env）
│   ├── schemas/          # Pydantic 工具参数模型
│   ├── tools/            # 路径校验 + 三个文件工具 + LangChain 注册
│   └── agent/            # 模型客户端 + Agent 组装
└── tests/
    ├── test_smoke.py
    ├── test_paths.py
    ├── test_tools.py
    └── test_agent.py
```

（`.venv/`、`.tmp/`、`.pytest-tmp/` 为本地生成，已被 gitignore。）

## 环境与依赖管理

- **Python**：`>=3.11`（当前开发机 3.14.5）。
- **依赖管理**：`venv + pip + pyproject.toml`（PEP 621），未引入 uv/poetry。
- **运行时依赖**：`langchain`、`langchain-core`、`langchain-openai`、`pydantic`、`pydantic-settings`。
- **开发依赖**：`pytest`。

### 安装

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[dev]"
```

### 运行测试

```powershell
.venv\Scripts\python.exe -m pytest -v
```

## 安全约定

- **密钥**：只放 `.env`，经 `Settings` 从环境变量读取；`.env` 已 gitignore，`.env.example` 只含占位符。
- **文件操作**：所有文件工具经 `PathResolver` 做 `resolve()` 前缀校验，仅限 `WORKPILOT_ALLOWED_DIRS` 授权目录，拒绝 `../`、越界绝对路径与符号链接逃逸。
- **数据**：用户文档、日志、向量库数据一律不入库（`data/`、`logs/`、`chroma/` 已忽略）。

## 未解决问题

- **文档格式**：仅支持 txt/md 文本；PDF（pdfplumber / pypdf）、Word（python-docx）、Excel（openpyxl）选型未定。
- **LLM 供应商**：采用 OpenAI 兼容协议；具体供应商与模型名经 `.env` 配置，真实 API 调用需人工提供密钥验收（测试中不连真实模型）。
- **langsmith 弃用告警**：测试输出 13 条 `asyncio.iscoroutinefunction` 弃用告警，来自第三方 `langsmith`，暂不处理。
- **沙盒限制**：`pip install` / `python -m venv` 需无沙盒执行；pytest 的 `tmp_path` 依赖 `conftest.py` 重定向临时目录并放宽目录 mode（详见 `conftest.py` 注释）。
