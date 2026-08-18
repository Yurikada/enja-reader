"""Light Markdown/plain-text parser producing translation-ready blocks.

Blocks keep enough structure for the viewer (headings, paragraphs, list
items, code fences, blockquotes). Inline markdown is left as-is; code
fences are never sent to the translator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Block:
    kind: str  # "heading" | "paragraph" | "list_item" | "code" | "quote"
    text: str
    level: int = 0  # heading level or list indent depth
    sentences: list[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def parse_document(text: str) -> list[Block]:
    blocks: list[Block] = []
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append(Block("paragraph", " ".join(para)))
            para.clear()

    while i < len(lines):
        line = lines[i]

        if _FENCE_RE.match(line):
            flush_para()
            fence = _FENCE_RE.match(line).group(1)
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                code_lines.append(lines[i])
                i += 1
            blocks.append(Block("code", "\n".join(code_lines)))
            i += 1
            continue

        m = _HEADING_RE.match(line)
        if m:
            flush_para()
            blocks.append(Block("heading", m.group(2).strip(), level=len(m.group(1))))
            i += 1
            continue

        m = _LIST_RE.match(line)
        if m:
            flush_para()
            item = [m.group(3).strip()]
            depth = len(m.group(1))
            i += 1
            # hanging continuation lines of the same item
            while i < len(lines) and lines[i].strip() and not _LIST_RE.match(lines[i]) \
                    and not _HEADING_RE.match(lines[i]) and not _FENCE_RE.match(lines[i]):
                item.append(lines[i].strip())
                i += 1
            blocks.append(Block("list_item", " ".join(item), level=depth))
            continue

        if line.strip().startswith(">"):
            flush_para()
            quote = [line.strip().lstrip("> ").strip()]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip("> ").strip())
                i += 1
            blocks.append(Block("quote", " ".join(q for q in quote if q)))
            continue

        if not line.strip():
            flush_para()
            i += 1
            continue

        para.append(line.strip())
        i += 1

    flush_para()
    return blocks
