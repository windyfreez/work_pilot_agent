"""把文件工具包装为 LangChain 工具并注册。"""

from langchain_core.tools import BaseTool, tool

from workpilot.config import Settings
from workpilot.schemas.tools import CreateDocumentInput, ListFilesInput, ReadDocumentInput

from . import files
from ._paths import PathResolver


def build_tools(settings: Settings) -> list[BaseTool]:
    """根据配置构造已绑定授权目录的文件工具列表。"""
    resolver = PathResolver(settings.allowed_dirs)
    max_bytes = settings.read_max_bytes

    @tool(args_schema=ListFilesInput)
    def list_files(directory: str, recursive: bool = False) -> list[str]:
        """列出授权目录内指定目录下的文件，返回相对路径列表。"""
        return files.list_files(resolver, directory, recursive)

    @tool(args_schema=ReadDocumentInput)
    def read_document(path: str) -> str:
        """读取授权目录内文本文件的内容（UTF-8，大小受限）。"""
        return files.read_document(resolver, path, max_bytes)

    @tool(args_schema=CreateDocumentInput)
    def create_document(path: str, content: str) -> str:
        """在授权目录内创建（或覆盖）文本文件，返回其绝对路径。"""
        return files.create_document(resolver, path, content)

    return [list_files, read_document, create_document]
