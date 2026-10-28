# WorkPilot Agent

一个能够执行办公任务的智能 Agent：支持文档读取与生成、多步骤任务执行、RAG 知识库问答、执行日志与结果验证。

> **当前状态：阶段 0 —— 项目初始化与基础配置。** 尚未实现 Agent、RAG、MCP 或前端功能。

## 项目目标

- **文档读写**：读取与生成常见办公文档（Markdown / 纯文本起步，后续扩展 PDF / Word / Excel）。
- **多步骤执行**：通过工作流编排完成复合办公任务（如「读取文件 → 分析 → 生成报告」）。
- **RAG 问答**：基于本地向量库（Chroma）进行知识库问答。
- **可审计**：记录执行日志，并对任务结果做校验。

## 功能边界（阶段 0）

本阶段**仅**完成工程脚手架与规范，**不实现**任何业务功能：

- ✅ 项目结构、依赖管理、测试框架、文档与开发规范。
- ⛔ Agent 运行时、LLM 接入、工具调用、RAG、MCP、前端。

功能边界随 `docs/roadmap.md` 逐步扩展。

## 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 语言 | Python 3.11+（当前开发环境 3.14.5） | 后端 |
| 模型接入 | LangChain | LLM 与工具调用（阶段 3） |
| 工作流 | LangGraph | 有状态编排（阶段 4） |
| API | FastAPI | 后端接口（阶段 1） |
| 校验 | Pydantic | 参数与结构化数据（阶段 1） |
| 知识库 | Chroma | 本地向量库（阶段 5） |
| 前端 | Vue 3 | 后续开发（阶段 7） |

## 目录结构

```
work_pilot_agent/
├── .gitignore            # 忽略 .venv / .env / 日志 / 数据等
├── .env.example          # 环境变量模板（仅占位符）
├── AGENTS.md             # AI Coding 开发规范
├── README.md
├── pyproject.toml        # 依赖与测试配置（PEP 621）
├── docs/
│   ├── architecture.md   # 架构设计
│   └── roadmap.md        # 分阶段路线图
├── src/
│   └── workpilot/        # 源码包（src 布局）
│       └── __init__.py
└── tests/
    └── test_smoke.py     # 冒烟测试
```

（`.venv/` 与 `.tmp/` 为本地生成，已被 gitignore，不显示。）

## 环境与依赖管理

- **Python**：`>=3.11`（当前开发机仅装 3.14.5）。
- **依赖管理**：`venv + pip + pyproject.toml`（PEP 621）。未引入 uv/poetry，避免额外工具依赖。
- **阶段 0 唯一新增依赖**：`pytest`（测试框架，`[project.optional-dependencies].dev`）。
  - 运行时依赖 `dependencies = []`；LangChain/LangGraph/FastAPI/Pydantic/Chroma 在各自阶段引入，见 `docs/roadmap.md`。

### 初始化命令（本机已执行）

```powershell
git init
python -m venv .venv
.venv\Scripts\python.exe -m pip install --no-cache-dir --upgrade pip pytest
```

### 运行测试

```powershell
.venv\Scripts\python.exe -m pytest -v
```

## 安全约定

- **密钥**：只放 `.env`；`.env` 已被 `.gitignore` 忽略，`.env.example` 只含占位符、不写真实值。
- **文件操作**：Agent 读写文件必须基于 `WORKPILOT_ALLOWED_DIRS` 授权目录做路径解析与校验，拒绝越界路径。
- **数据**：用户文档、日志、向量库数据一律不入库（`data/`、`logs/`、`chroma/` 已忽略）。

## 未解决问题

- **Python 3.14 兼容性**：LangChain/LangGraph/pydantic-core 对 CPython 3.14 的 wheel 支持待验证；若阶段 1 安装失败，需固定到 3.12/3.13。
- **LLM 供应商与模型**：尚未选定（OpenAI / Anthropic / DeepSeek 等），阶段 3 前需确定。
- **文档格式解析库**：PDF（pdfplumber / pypdf）、Word（python-docx）、Excel（openpyxl）选型未定。
- **沙盒限制**：`python -m venv` 与 `pip install` 依赖 tempfile 临时目录，需在无沙盒限制下执行（详见阶段 0 交付记录）。
