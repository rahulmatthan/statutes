"""Shared parsing library for Indian gazette-style legal documents.

The Aadhaar Act and the rules and regulations made under it follow the same
gazette layout:

    1. Heading.—(1) Sub-section text...
       (a) clause text;
       (b) clause text:
            Provided that ...
            Explanation.—...

Amendments inside the body are marked `N[...]` where N is a footnote number
(reset per page); the corresponding footnote at the foot of the page records
"Subs. by …" / "Ins. by …" / "Omitted by …" with the amending instrument.

This module provides the shared logic; specific document types provide their
own header/footnote patterns and run the pipeline.
"""

from __future__ import annotations
import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional


# ---------------------------------------------------------------------------
# Block-break detection
# ---------------------------------------------------------------------------

ROMANS = [
    "ii", "iii", "iv", "vi", "vii", "viii", "ix",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
]
_ROMAN_ALT = "|".join(ROMANS)

_REF_WORDS = (
    "sub-section", "subsection", "sub-clause", "subclause",
    "section", "sections", "clause", "clauses",
    "sub-regulation", "subregulation", "regulation", "regulations",
    "rule", "rules", "item", "items", "paragraph", "paragraphs",
    "chapter", "chapters", "form", "schedule", "of", "and", "or",
)
_REF_PRECEDES = re.compile(
    r"(?:" + "|".join(re.escape(w) for w in _REF_WORDS) + r")\s*$",
    re.IGNORECASE,
)

_TOKEN_PATTERNS: list[tuple[re.Pattern, str, bool]] = [
    (re.compile(rf"\((?:{_ROMAN_ALT})\)"), "subclause", True),
    (re.compile(r"\(\d+[a-z]?\)"), "subsection", True),
    (re.compile(r"\([a-z]{1,3}\)"), "clause", True),
    (re.compile(r"Provided\s+(?:that|further\s+that|also)\b"), "proviso", False),
    (re.compile(r"Explanation\s*[—–-]"), "explanation", False),
    (re.compile(r"Illustration\s*[—–-]"), "explanation", False),
]

_CLASS_PRIORITY = {
    "subsection": 0, "subclause": 1, "clause": 2, "proviso": 3, "explanation": 4,
}

BREAK_TOKEN = "\x00BREAK\x00"

_SPAN_OPEN_RE = re.compile(r'<span class="amend"[^>]*>')


def _amend_span_regions(s: str) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    open_starts: list[int] = []
    i = 0
    while i < len(s):
        if s.startswith("<span ", i):
            m = _SPAN_OPEN_RE.match(s, i)
            if m:
                open_starts.append(m.end())
                i = m.end()
                continue
        if s.startswith("</span>", i):
            if open_starts:
                start = open_starts.pop()
                regions.append((start, i))
            i += len("</span>")
            continue
        i += 1
    return regions


def _amend_span_open_tags(s: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in _SPAN_OPEN_RE.finditer(s):
        out[m.end()] = m.group(0)
    return out


def _active_span_at(idx: int, regions, open_tags) -> str | None:
    for start, end in regions:
        if start <= idx < end:
            return open_tags.get(start)
    return None


def _is_inside_tag(s: str, idx: int) -> bool:
    last_lt = s.rfind("<", 0, idx)
    last_gt = s.rfind(">", 0, idx)
    return last_lt > last_gt


def insert_block_breaks(text: str) -> str:
    """Insert BREAK tokens before each opener (sub-section / clause / etc.).

    Cross-references like `sub-section (3)` are excluded by inspecting the
    preceding word. Openers inside an active amendment span trigger a
    close/reopen so paragraphs remain self-contained.
    """
    s = re.sub(r"\s+", " ", text).strip()

    span_regions = _amend_span_regions(s)

    candidates: list[tuple[int, int, str, str]] = []
    for pattern, cls, needs_check in _TOKEN_PATTERNS:
        for m in pattern.finditer(s):
            start = m.start()
            if _is_inside_tag(s, start):
                continue
            if start > 0 and not s[start - 1].isspace():
                if s[start - 1] != ">":
                    continue
            if needs_check:
                preceding = s[max(0, start - 30):start].rstrip()
                preceding_text = re.sub(r"<[^>]+>", " ", preceding).rstrip()
                list_sep = re.search(
                    r"[;,]\s+(?:and|or)\s*$", preceding_text,
                )
                if not list_sep and _REF_PRECEDES.search(preceding_text):
                    continue
            candidates.append((start, m.end(), cls, m.group(0)))

    candidates.sort(
        key=lambda c: (c[0], _CLASS_PRIORITY.get(c[2], 99)),
    )
    seen_starts: set[int] = set()
    chosen: list[tuple[int, int, str, str]] = []
    for c in candidates:
        if c[0] in seen_starts:
            continue
        seen_starts.add(c[0])
        chosen.append(c)
    chosen.sort(key=lambda c: c[0])

    open_spans = _amend_span_open_tags(s)

    out: list[str] = []
    cursor = 0
    for start, end, cls, token in chosen:
        ws_start = start
        while ws_start > cursor and s[ws_start - 1].isspace():
            ws_start -= 1
        prev = s[cursor:ws_start]
        active_span = _active_span_at(start, span_regions, open_spans)
        if active_span is not None:
            if prev.endswith(active_span):
                out.append(prev[: -len(active_span)])
                out.append(f"{BREAK_TOKEN}{cls}|")
                out.append(active_span)
            else:
                out.append(prev)
                out.append("</span>")
                out.append(f"{BREAK_TOKEN}{cls}|")
                out.append(active_span)
        else:
            out.append(prev)
            out.append(f"{BREAK_TOKEN}{cls}|")
        out.append(token)
        cursor = end
    out.append(s[cursor:])
    return "".join(out)


_BLOCK_AMEND_RE = re.compile(
    r'^<span class="amend"([^>]*)>(.*)</span>$', re.DOTALL,
)


def render_body_html(text_with_breaks: str) -> str:
    """Convert break-tokenised text into <p class="block …"> paragraphs."""
    parts = text_with_breaks.split(BREAK_TOKEN)
    blocks: list[tuple[str, str]] = []
    head = parts[0].strip()
    if head:
        blocks.append(("lead", head))
    for p in parts[1:]:
        cls, _, body = p.partition("|")
        body = body.strip()
        if body:
            blocks.append((cls, body))

    out_lines: list[str] = []
    for cls, body in blocks:
        body = body.strip()
        m = _BLOCK_AMEND_RE.match(body)
        if m:
            attrs = m.group(1)
            inner = m.group(2)
            body = f'<span class="amend amend-block"{attrs}>{inner}</span>'
        out_lines.append(f'  <p class="block {cls}">{body}</p>')
    return "<div class=\"statute-body\">\n" + "\n".join(out_lines) + "\n</div>"


# ---------------------------------------------------------------------------
# Inline marker replacement
# ---------------------------------------------------------------------------

def _open_amend_span(key: str, amend: dict) -> str:
    parts = ['<span class="amend"']
    parts.append(f' data-id="{html.escape(key)}"')
    parts.append(f' data-kind="{html.escape(amend["kind"])}"')
    parts.append(f' data-date="{html.escape(amend["date"])}"')
    parts.append(f' data-by="{html.escape(amend["by"])}"')
    if amend.get("by_text"):
        parts.append(f' data-by-text="{html.escape(amend["by_text"])}"')
    if amend.get("target"):
        parts.append(f' data-target="{html.escape(amend["target"])}"')
    if amend.get("before"):
        parts.append(f' data-before="{html.escape(amend["before"])}"')
    if amend.get("note"):
        parts.append(f' data-note="{html.escape(amend["note"])}"')
    parts.append(">")
    return "".join(parts)


def replace_amendment_markers(
    text: str, amendments: dict, page_idx: int,
) -> str:
    """Replace `<digit>[...]` markers with `<span class="amend" …>`.

    Accepts `3[`, `3 [`, and `3\\n[` (PDF extraction sometimes inserts a
    line-break between the marker number and the bracket).
    """
    out: list[str] = []
    stack: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isdigit() and i + 1 < n:
            j = i
            while j < n and text[j].isdigit():
                j += 1
            # Skip whitespace between digit and `[`.
            k = j
            while k < n and text[k] in " \t\n":
                k += 1
            if k < n and text[k] == "[" and (
                i == 0 or not text[i - 1].isalnum()
            ):
                fnum = int(text[i:j])
                key = f"p{page_idx}.{fnum}"
                amend = amendments.get(key)
                if amend is not None:
                    out.append(_open_amend_span(key, amend))
                    stack.append("amend")
                    i = k + 1
                    continue
                out.append(text[i])
                i += 1
                continue
        if c == "]" and stack:
            stack.pop()
            out.append("</span>")
            i += 1
            continue
        out.append(c)
        i += 1
    while stack:
        out.append("</span>")
        stack.pop()
    return "".join(out)


# ---------------------------------------------------------------------------
# Trailing-bracket cleanup
# ---------------------------------------------------------------------------

def strip_trailing_section_close_bracket(html_body: str) -> str:
    return re.sub(r"\]\s*</p>\s*</div>\s*$", "</p></div>", html_body)


# ---------------------------------------------------------------------------
# Manual-edit guard
# ---------------------------------------------------------------------------

def is_manual_edit(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        head = path.read_text().split("---", 2)
    except OSError:
        return False
    if len(head) < 2:
        return False
    return bool(
        re.search(r"^\s*manual_edit\s*:\s*true\s*$", head[1], re.MULTILINE),
    )


# ---------------------------------------------------------------------------
# Generic body cleanup
# ---------------------------------------------------------------------------

def clean_body_text(body: str) -> str:
    """First-pass whitespace cleanup before marker replacement and breaks."""
    body = re.sub(r"\n[ \t]{4,}", "\n", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    return body
