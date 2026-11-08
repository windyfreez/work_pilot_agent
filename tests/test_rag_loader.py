"""文档导入与格式解析的单元测试。"""

import pytest

from workpilot.rag import parse_directory, parse_file
from workpilot.rag.loader import UnsupportedFormatError


def test_parse_txt(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    d = parse_file(f)
    assert d.format == "txt"
    assert d.filename == "a.txt"
    assert d.text == "hello world"


def test_parse_md(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# title\ncontent", encoding="utf-8")
    d = parse_file(f)
    assert d.format == "md"
    assert "# title" in d.text


def test_parse_docx(tmp_path):
    import docx

    f = tmp_path / "a.docx"
    doc = docx.Document()
    doc.add_paragraph("hello docx")
    doc.add_paragraph("second para")
    doc.save(str(f))

    d = parse_file(f)
    assert d.format == "docx"
    assert "hello docx" in d.text
    assert "second para" in d.text


def test_parse_xlsx(tmp_path):
    import openpyxl

    f = tmp_path / "a.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["name", "value"])
    ws.append(["foo", 42])
    wb.save(str(f))

    d = parse_file(f)
    assert d.format == "xlsx"
    assert "Data" in d.text
    assert "foo" in d.text


def test_parse_pdf(tmp_path):
    from reportlab.pdfgen import canvas

    f = tmp_path / "a.pdf"
    c = canvas.Canvas(str(f))
    c.drawString(72, 720, "hello pdf")
    c.save()

    d = parse_file(f)
    assert d.format == "pdf"
    assert "hello pdf" in d.text


def test_parse_unsupported(tmp_path):
    f = tmp_path / "a.xyz"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        parse_file(f)


def test_parse_directory(tmp_path):
    (tmp_path / "a.md").write_text("A", encoding="utf-8")
    (tmp_path / "b.txt").write_text("B", encoding="utf-8")
    (tmp_path / "skip.xyz").write_text("C", encoding="utf-8")
    docs = parse_directory(tmp_path)
    assert sorted(d.filename for d in docs) == ["a.md", "b.txt"]
