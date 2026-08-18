"""Parsers producing translation-ready blocks.

- Markdown/plain text: light line-based parser (headings, paragraphs,
  list items, code fences, blockquotes). Inline markdown is left as-is.
- HTML: stdlib html.parser extraction of the same block kinds.

Code blocks are never sent to the translator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class Block:
    kind: str  # "heading" | "paragraph" | "list_item" | "code" | "quote"
    text: str
    level: int = 0  # heading level or list indent depth
    ordered: bool = False  # list_item: numbered vs bullet
    number: int = -1  # list_item: explicit number of an ordered item (-1 = unknown)
    sentences: list[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def _closes_fence(line: str, fence: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith(fence[0] * len(fence))
        and set(stripped) == {fence[0]}
    )


def parse_markdown(text: str) -> list[Block]:
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

        fence_m = _FENCE_RE.match(line)
        if fence_m:
            flush_para()
            fence = fence_m.group(1)
            code_lines = []
            i += 1
            while i < len(lines) and not _closes_fence(lines[i], fence):
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
            indent, marker, rest = m.group(1), m.group(2), m.group(3)
            item = [rest.strip()]
            i += 1
            # hanging continuation lines of the same item
            while i < len(lines) and lines[i].strip() and not _LIST_RE.match(lines[i]) \
                    and not _HEADING_RE.match(lines[i]) and not _FENCE_RE.match(lines[i]):
                item.append(lines[i].strip())
                i += 1
            ordered = marker[0].isdigit()
            blocks.append(
                Block(
                    "list_item",
                    " ".join(item),
                    level=len(indent) // 2,
                    ordered=ordered,
                    number=int(marker[:-1]) if ordered else -1,
                )
            )
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


_SKIP_TAGS = {"head", "title", "script", "style", "nav", "footer", "header",
              "aside", "noscript", "svg", "form", "button", "select",
              "template", "iframe"}
# tags that end any text run even though we don't extract them directly
_BOUNDARY_TAGS = {"div", "section", "article", "main", "body", "table", "tr",
                  "td", "th", "figure", "figcaption", "dl", "dt", "dd",
                  "details", "summary", "hr"}
_WS_RE = re.compile(r"\s+")


class _HTMLBlockExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._skip_depth = 0
        self._pre_depth = 0
        self._quote_depth = 0
        # one entry per open <ul>/<ol>: {"ordered": bool, "n": next item number}
        self._list_stack: list[dict] = []
        self._current: Block | None = None
        self._buf: list[str] = []

    def _flush(self) -> None:
        if self._current is not None:
            text = self._buf and "".join(self._buf) or ""
            if self._current.kind != "code":
                text = _WS_RE.sub(" ", text).strip()
            else:
                text = text.strip("\n")
            if text:
                self._current.text = text
                self.blocks.append(self._current)
        self._current = None
        self._buf = []

    def _open(self, block: Block) -> None:
        self._flush()
        self._current = block

    def _in_list_item(self) -> bool:
        return self._current is not None and self._current.kind == "list_item"

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "pre":
            self._pre_depth += 1
            self._open(Block("code", ""))
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._open(Block("heading", "", level=int(tag[1])))
        elif tag == "p":
            if self._in_list_item():
                self._buf.append(" ")
            else:
                kind = "quote" if self._quote_depth else "paragraph"
                self._open(Block(kind, ""))
        elif tag == "li":
            entry = self._list_stack[-1] if self._list_stack else None
            ordered = entry["ordered"] if entry else False
            number = -1
            if entry and ordered:
                number = entry["n"]
                entry["n"] += 1
            self._open(Block("list_item", "",
                             level=max(len(self._list_stack) - 1, 0),
                             ordered=ordered, number=number))
        elif tag in {"ul", "ol"}:
            self._flush()
            start = dict(attrs).get("start") if tag == "ol" else None
            n = int(start) if start and str(start).lstrip("-").isdigit() else 1
            self._list_stack.append({"ordered": tag == "ol", "n": n})
        elif tag == "blockquote":
            self._flush()
            self._quote_depth += 1
        elif tag in _BOUNDARY_TAGS:
            if self._in_list_item():
                self._buf.append(" ")
            else:
                self._flush()
        elif tag == "br" and self._current is not None:
            self._buf.append("\n" if self._pre_depth else " ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(self._skip_depth - 1, 0)
            return
        if self._skip_depth:
            return
        if tag == "pre":
            self._pre_depth = max(self._pre_depth - 1, 0)
            self._flush()
        elif tag == "p":
            if self._in_list_item():
                self._buf.append(" ")
            else:
                self._flush()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6", "li"}:
            self._flush()
        elif tag in {"ul", "ol"}:
            self._flush()
            if self._list_stack:
                self._list_stack.pop()
        elif tag == "blockquote":
            self._flush()
            self._quote_depth = max(self._quote_depth - 1, 0)
        elif tag in _BOUNDARY_TAGS:
            if self._in_list_item():
                self._buf.append(" ")
            else:
                self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._current is None:
            # bare text directly inside body/div/article/blockquote
            if data.strip():
                kind = "quote" if self._quote_depth else "paragraph"
                self._current = Block(kind, "")
                self._buf = [data]
            return
        self._buf.append(data)


def parse_html(text: str) -> list[Block]:
    extractor = _HTMLBlockExtractor()
    extractor.feed(text)
    extractor._flush()
    return extractor.blocks


def parse_document(text: str, fmt: str = "markdown") -> list[Block]:
    if fmt == "html":
        return parse_html(text)
    return parse_markdown(text)
