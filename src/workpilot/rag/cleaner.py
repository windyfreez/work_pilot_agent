"""文本清洗。"""

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """清洗文本：去控制符、统一换行、压缩空白、去首尾空白。"""
    text = _CONTROL_CHARS.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)  # 压缩行内空白
    text = re.sub(r"\n{3,}", "\n\n", text)  # 压缩多余空行
    return text.strip()
