"""API 请求模型。"""

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    """创建任务请求。"""

    input: str = Field(description="任务描述（自然语言）")


class ApprovalRequest(BaseModel):
    """审批请求。"""

    approved: bool = Field(description="是否批准")


class DocumentImportRequest(BaseModel):
    """知识库文档导入请求。"""

    paths: list[str] = Field(description="要导入的文件或目录路径列表")


class KnowledgeSearchRequest(BaseModel):
    """知识库检索请求。"""

    query: str = Field(description="检索问题")
    top_k: int = Field(default=4, description="返回条数")
