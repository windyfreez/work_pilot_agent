"""文档导入与格式解析。"""

from dataclasses import dataclass, field
from pathlib import Path

TEXT_FORMATS = {"txt", "md", "markdown"}
SUPPORTED_FORMATS = TEXT_FORMATS | {"pdf", "docx", "xlsx"}


@dataclass
class ParsedDocument:
    """解析后的文档。"""

    source: str  # 完整路径
    filename: str  # 文件名
    format: str  # 格式（txt/md/pdf/docx/xlsx）
    text: str  # 提取出的纯文本
    metadata: dict = field(default_factory=dict)


class UnsupportedFormatError(ValueError):
    """不支持的文档格式。"""


def parse_file(path: str | Path) -> ParsedDocument:
    """解析单个文档为纯文本。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")
    if not p.is_file():
        raise ValueError(f"不是文件：{p}")

    fmt = p.suffix.lower().lstrip(".")
    if fmt in TEXT_FORMATS:
        return _parse_text(p)
    if fmt == "pdf":
        return _parse_pdf(p)
    if fmt == "docx":
        return _parse_docx(p)
    if fmt == "xlsx":
        return _parse_xlsx(p)
    raise UnsupportedFormatError(f"不支持的文档格式：{fmt}")


def parse_directory(path: str | Path, recursive: bool = True) -> list[ParsedDocument]:
    """解析目录下所有支持的文档。"""
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"不是目录：{root}")

    files = sorted(root.rglob("*")) if recursive else sorted(root.iterdir())
    docs: list[ParsedDocument] = []
    for f in files:
        if f.is_file() and f.suffix.lower().lstrip(".") in SUPPORTED_FORMATS:
            docs.append(parse_file(f))
    return docs


def _parse_text(p: Path) -> ParsedDocument:
    return ParsedDocument(
        source=str(p.resolve()),
        filename=p.name,
        format=p.suffix.lower().lstrip("."),
        text=p.read_text(encoding="utf-8"),
    )


def _parse_pdf(p: Path) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(str(p))
    pages = [page.extract_text() or "" for page in reader.pages]
    return ParsedDocument(
        source=str(p.resolve()),
        filename=p.name,
        format="pdf",
        text="\n\n".join(pages),
        metadata={"pages": len(reader.pages)},
    )


def _parse_docx(p: Path) -> ParsedDocument:
    from docx import Document

    doc = Document(str(p))
    parts = [para.text for para in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return ParsedDocument(
        source=str(p.resolve()),
        filename=p.name,
        format="docx",
        text="\n".join(parts),
        metadata={"paragraphs": len(doc.paragraphs), "tables": len(doc.tables)},
    )


def _parse_xlsx(p: Path) -> ParsedDocument:
    import openpyxl

    wb = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    sheets: list[str] = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                rows.append(" | ".join(cells))
        sheets.append(f"# Sheet: {ws.title}\n" + "\n".join(rows))
    wb.close()
    return ParsedDocument(
        source=str(p.resolve()),
        filename=p.name,
        format="xlsx",
        text="\n\n".join(sheets),
        metadata={"sheets": [ws.title for ws in wb.worksheets]},
    )
