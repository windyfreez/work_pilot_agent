"""文件工具的 Pydantic 输入参数模型。"""

from pydantic import BaseModel, Field


class ListFilesInput(BaseModel):
    """list_files 工具参数。"""

    directory: str = Field(description="要列出的目录（授权目录内的相对或绝对路径）")
    recursive: bool = Field(default=False, description="是否递归列出子目录")


class ReadDocumentInput(BaseModel):
    """read_document 工具参数。"""

    path: str = Field(description="要读取的文档路径（授权目录内）")


class CreateDocumentInput(BaseModel):
    """create_document 工具参数。"""

    path: str = Field(description="要创建/覆盖的文档路径（授权目录内）")
    content: str = Field(description="文档文本内容")
