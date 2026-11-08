"""文本分块（自实现，避免额外依赖）。"""

import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """把文本切成约 ``chunk_size`` 大小的块，块间有 ``chunk_overlap`` 重叠。

    优先按段落切，避免在句子中间硬切；单段超过 chunk_size 时按字符硬切。
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
            continue
        candidate = f"{current}\n\n{para}"
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            current = f"{current[-chunk_overlap:]}\n\n{para}" if chunk_overlap > 0 else para
    if current:
        chunks.append(current)

    # 硬切超长块（单个段落超过 chunk_size）
    result: list[str] = []
    for c in chunks:
        if len(c) <= chunk_size:
            result.append(c)
            continue
        start = 0
        while start < len(c):
            end = min(start + chunk_size, len(c))
            result.append(c[start:end])
            if end >= len(c):
                break
            start = end - chunk_overlap if chunk_overlap > 0 else end

    return [c for c in result if c.strip()]
