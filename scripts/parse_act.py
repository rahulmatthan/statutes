"""Parse the consolidated Aadhaar Act PDF text into per-section markdown files.

Input:  source-pdfs/extracted/act-current.txt  (output of `pdftotext -layout`)
Output: src/content/sections/s-<n>.md           (one per section)

The body is emitted as semantic HTML so the section page can:
  - Show each sub-section / clause / sub-clause on its own line
  - Render inline amendment markers (`<span class="amend" data-...>`)
  - Toggle between current and historical versions of the text
"""

from __future__ import annotations
import html
import re
from pathlib import Path
from collections import OrderedDict

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source-pdfs/extracted/act-current.txt"
OUT = ROOT / "src/content/sections"

CHAPTER_RE = re.compile(r"^\s+CHAPTER\s+([IVX]+[A-Z]*)\s*$")
CHAPTER_TITLE_RE = re.compile(r"^\s+([A-Z][A-Z, ]+[A-Z])\s*$")
# Section start. The optional `\d+\[` prefix marks a section whose entire
# content was substituted/inserted by a footnote N (e.g., `1[21. Officers ...`).
SECTION_START_RE = re.compile(r"^\s+(?:(\d+)\[)?(\d+[A-Z]?)\.\s+([A-Z].*)$")
SECTION_END_TOKEN = ".—"
FOOTNOTE_DEF_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")

CHAPTERS = OrderedDict([
    ("I", "Preliminary"),
    ("II", "Enrolment"),
    ("III", "Authentication"),
    ("IV", "Unique Identification Authority of India"),
    ("V", "Grants, Accounts and Audit and Annual Report"),
    ("VI", "Protection of Information"),
    ("VIA", "Civil Penalties"),
    ("VII", "Offences and Penalties"),
    ("VIII", "Miscellaneous"),
])

CHAPTER_ORDER = {k: i + 1 for i, k in enumerate(CHAPTERS)}


def is_running_title(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if "The Aadhaar (Targeted Delivery" in line:
        return True
    if "Subsidies, Benefits and Services) Act, 2016" in line:
        return True
    if re.match(r"^\d+\s*$", s):
        return True
    return False


# ---------------------------------------------------------------------------
# Page splitter (body vs. footnotes)
# ---------------------------------------------------------------------------

FOOTNOTE_LINE_RE = re.compile(r"^\s{0,5}(\d{1,2})\.\s+[A-Z]")
# Distinctive amendment-footnote opener — recognise even a single footnote.
AMEND_FOOTNOTE_RE = re.compile(
    r"^\s{0,5}\d+\.\s+(?:Ins\.|Subs\.|Omitted\b|Section\s+\d+,\s+before)"
)


def split_body_and_footnotes(page: str) -> tuple[str, list[tuple[int, str]]]:
    """Split a page into body lines and footnote definitions.

    Each page may have one or many footnotes. We detect the start by either:
      (a) a `1.` line whose body looks like an amendment footnote
          (Ins./Subs./Omitted by ...), or
      (b) a `1.` line followed within ~12 lines by a `2.` line.
    The section's main numbering uses parentheses, so a bare `N.` at the start
    of a line is reliably a footnote.
    """
    lines = page.split("\n")

    # Candidate footnote-numbered lines.
    candidates: list[tuple[int, int]] = []  # (line_idx, footnote_num)
    for i, line in enumerate(lines):
        m = FOOTNOTE_LINE_RE.match(line)
        if m:
            num = int(m.group(1))
            candidates.append((i, num))

    foot_start = None
    for idx, (li, num) in enumerate(candidates):
        if num != 1:
            continue
        # Skip the "section 1" header on page 0 — the section header has ".—".
        if SECTION_END_TOKEN in lines[li]:
            continue
        # Accept if the line itself looks like an amendment footnote …
        if AMEND_FOOTNOTE_RE.match(lines[li]):
            foot_start = li
            break
        # … or if a `2.` follows within 12 lines.
        for li2, num2 in candidates[idx + 1: idx + 8]:
            if num2 == 2 and li2 - li <= 12:
                foot_start = li
                break
        if foot_start is not None:
            break

    if foot_start is None:
        return "\n".join(lines), []

    body = "\n".join(lines[:foot_start])
    footers: list[tuple[int, str]] = []
    cur_num: int | None = None
    cur_buf: list[str] = []
    for line in lines[foot_start:]:
        if is_running_title(line):
            continue
        m = FOOTNOTE_DEF_RE.match(line)
        if m and len(m.group(1)) <= 2:
            if cur_num is not None:
                footers.append((cur_num, "\n".join(cur_buf).strip()))
            cur_num = int(m.group(1))
            cur_buf = [m.group(2).rstrip()]
        else:
            if cur_num is not None:
                cur_buf.append(line.rstrip())
    if cur_num is not None:
        footers.append((cur_num, "\n".join(cur_buf).strip()))
    return body, footers


# ---------------------------------------------------------------------------
# Footnote → amendment record
# ---------------------------------------------------------------------------

def parse_amendment_footnote(num: int, text: str) -> dict | None:
    t = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()

    if t.startswith("Ins. by"):
        kind = "inserted"
    elif t.startswith("Subs. by"):
        kind = "substituted"
    elif t.startswith("Omitted by"):
        kind = "omitted"
    else:
        return None

    # Pattern: "Subs. by <act>, sec. <amending-section>[, for <target>] [w.e.f. <date>]"
    # The target is the substring between ", for " and the next "[" or end of citation.
    m = re.match(
        r"^(Ins\.|Subs\.|Omitted) by (.+?),\s+(?:sec|secs)\.\s*([0-9A-Za-z()]+)"
        r"(?:,\s+for\s+([^\[]+))?"
        r"\s*(?:\[w\.e\.f\.\s*([0-9-]+))?",
        t,
    )
    by_text = ""
    target = None
    date = None
    if m:
        by_text = m.group(2).strip()
        target = m.group(4).strip(' ".,') if m.group(4) else None
        raw_date = m.group(5)
        if raw_date:
            parts = raw_date.split("-")
            if len(parts) == 3:
                d, mn, y = parts
                date = f"{y}-{int(mn):02d}-{int(d):02d}"

    if "Act 14 of 2019" in t:
        by_slug = "2019-amendment-act"
    elif "Ordinance" in t:
        by_slug = "2019-ordinance"
    elif "Jan Vishwas" in t:
        by_slug = "2023-jan-vishwas"
    elif "Jammu and Kashmir Reorganisation" in t:
        by_slug = "2019-jk-reorganisation"
    else:
        by_slug = "unknown"

    before = None
    if kind == "substituted":
        bm = re.search(
            r"(?:before substitution|stood as under)[^\"“]*[\"“](.+?)[\"”]\s*\.?$",
            t,
            re.DOTALL,
        )
        if bm:
            before = re.sub(r"\s+", " ", bm.group(1)).strip()
        if not before:
            fm = re.search(r"for ['\"“]([^'\"”]+)['\"”]", t)
            if fm:
                before = fm.group(1).strip()

    note = None
    if kind == "inserted":
        note = f"Inserted by {by_text}" if by_text else "Inserted by amending instrument"
    elif kind == "substituted" and target:
        note = f"{target.strip().capitalize()} substituted by {by_text}" if by_text else None
    elif kind == "omitted" and target:
        note = f"{target.strip().capitalize()} omitted by {by_text}" if by_text else None

    return {
        "footnote": num,
        "kind": kind,
        "by": by_slug,
        "by_text": by_text,
        "target": target,
        "date": date or "2019-07-25",
        "before": before,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Body formatting → HTML
# ---------------------------------------------------------------------------

# Match an amendment marker like "1[" or "12[" (digit run followed by `[`).
MARKER_RE = re.compile(r"(\d{1,2})\[")

# Roman numerals up to xx — used to detect sub-clause markers like (i), (ii), …
# Multi-character romans only — single-char (i), (v), (x) collide with
# alphabetical clause openers (i.e., between (h) and (j)). We rely on the
# clause regex to handle those.
ROMANS = [
    "ii", "iii", "iv", "vi", "vii", "viii", "ix",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
]
_ROMAN_ALT = "|".join(ROMANS)

# Words that, when they immediately precede `(X)`, signal a cross-reference
# rather than a new opener — e.g., "sub-section (3)", "clause (a)".
_REF_WORDS = (
    "sub-section",
    "subsection",
    "sub-clause",
    "subclause",
    "section",
    "sections",
    "clause",
    "clauses",
    "item",
    "items",
    "paragraph",
    "paragraphs",
    "chapter",
    "chapters",
    "regulation",
    "regulations",
    "rule",
    "rules",
    "form",
    "schedule",
    "of",
    "and",
    "or",
)
_REF_PRECEDES = re.compile(
    r"(?:" + "|".join(re.escape(w) for w in _REF_WORDS) + r")\s*$",
    re.IGNORECASE,
)

# Token patterns recognised as block openers.
_TOKEN_PATTERNS: list[tuple[re.Pattern, str, bool]] = [
    # (regex, css_class, requires_opener_check)
    (re.compile(rf"\((?:{_ROMAN_ALT})\)"), "subclause", True),
    (re.compile(r"\(\d+[a-z]?\)"), "subsection", True),
    (re.compile(r"\([a-z]{1,3}\)"), "clause", True),
    (re.compile(r"Provided\s+(?:that|further\s+that|also)\b"), "proviso", False),
    (re.compile(r"Explanation\s*[—–-]"), "explanation", False),
    (re.compile(r"Illustration\s*[—–-]"), "explanation", False),
]

# Block-break sentinel used between transformations.
BREAK_TOKEN = "\x00BREAK\x00"


def replace_amendment_markers(
    text: str, amendments: dict, page_idx: int
) -> str:
    """Replace `<digit>[...]` markers with `<span class="amend" data-...>...</span>`.

    Operates on a single page's text so the page-local footnote number lookup
    is unambiguous.
    """
    out: list[str] = []
    stack: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c.isdigit() and i + 1 < n:
            # Find the run of digits.
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] == "[" and (i == 0 or not text[i - 1].isalnum()):
                fnum = int(text[i:j])
                key = f"p{page_idx}.{fnum}"
                amend = amendments.get(key)
                if amend is not None:
                    out.append(_open_amend_span(key, amend))
                    stack.append("amend")
                    i = j + 1
                    continue
                # No amendment for this marker — keep raw text.
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
    # Close any unclosed spans (defensive).
    while stack:
        out.append("</span>")
        stack.pop()
    return "".join(out)


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


def insert_block_breaks(text: str) -> str:
    """Insert BREAK tokens before each opener (sub-section / clause / etc.).

    We walk through the text and, for each candidate opener match, decide
    whether it's a real opener or a cross-reference (e.g., "sub-section (3)")
    by inspecting the preceding word. HTML span tags inserted earlier are
    preserved — we never break the markup of an open span.
    """
    s = re.sub(r"\s+", " ", text).strip()

    # Pre-compute span-region map. We *do* allow breaks inside amend spans
    # so that an amendment that starts a new sub-section becomes its own
    # paragraph; the span is closed and reopened around the break.
    span_regions = _amend_span_regions(s)

    candidates: list[tuple[int, int, str, str]] = []
    for pattern, cls, needs_check in _TOKEN_PATTERNS:
        for m in pattern.finditer(s):
            start = m.start()
            if _is_inside_tag(s, start):
                continue
            if start > 0 and not s[start - 1].isspace():
                # Allow openers immediately after `>` of a span tag
                # (i.e., the span content begins with the opener).
                prev = s[start - 1]
                if prev != ">":
                    continue
            if needs_check:
                preceding = s[max(0, start - 30):start].rstrip()
                # Strip any HTML tags from the preceding context so e.g.
                # "<span ...>(4)" looks like just "" preceding.
                preceding_text = re.sub(r"<[^>]+>", " ", preceding).rstrip()
                list_sep = re.search(r"[;,]\s+(?:and|or)\s*$", preceding_text)
                if not list_sep and _REF_PRECEDES.search(preceding_text):
                    continue
            candidates.append((start, m.end(), cls, m.group(0)))

    # De-overlap by start position; prefer earlier match. For ties, prefer
    # subsection > subclause > clause (numeric > roman > letter).
    candidates.sort(key=lambda c: (c[0], _CLASS_PRIORITY.get(c[2], 99)))
    seen_starts: set[int] = set()
    chosen: list[tuple[int, int, str, str]] = []
    for c in candidates:
        if c[0] in seen_starts:
            continue
        seen_starts.add(c[0])
        chosen.append(c)
    chosen.sort(key=lambda c: c[0])

    # Build output by inserting BREAK tokens. When inserting inside an open
    # amendment span, close the span before the break and reopen the same
    # span (with the same attributes) immediately after, so each resulting
    # paragraph has self-contained markup.
    open_spans = _amend_span_open_tags(s)  # idx -> opening tag string

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
                # The opener is at the very start of the span content; emit
                # the prev text without the span tag, then break + reopen.
                out.append(prev[: -len(active_span)])
                out.append(f"{BREAK_TOKEN}{cls}|")
                out.append(active_span)
            else:
                # Opener is mid-span; close before break and reopen after.
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


_CLASS_PRIORITY = {"subsection": 0, "subclause": 1, "clause": 2,
                   "proviso": 3, "explanation": 4}


def _is_inside_tag(s: str, idx: int) -> bool:
    """Return True if position idx is inside an HTML tag (between < and >)."""
    last_lt = s.rfind("<", 0, idx)
    last_gt = s.rfind(">", 0, idx)
    return last_lt > last_gt


_SPAN_OPEN_RE = re.compile(r'<span class="amend"[^>]*>')
_SPAN_CLOSE_RE = re.compile(r"</span>")


def _amend_span_regions(s: str) -> list[tuple[int, int]]:
    """Return list of (start, end) regions covered by amendment spans.

    `start` is the position immediately after the open tag's `>`; `end` is
    the position of the closing `</span>`.
    """
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
    """Map each span content-start position to its full opening tag string."""
    out: dict[int, str] = {}
    for m in _SPAN_OPEN_RE.finditer(s):
        out[m.end()] = m.group(0)
    return out


def _active_span_at(idx: int, regions, open_tags) -> str | None:
    """Return the opening-tag string of the amendment span covering idx, or None."""
    for start, end in regions:
        if start <= idx < end:
            # Find the opening tag that produced this region.
            return open_tags.get(start)
    return None


def _is_inside_span(idx: int, regions: list[tuple[int, int]]) -> bool:
    for start, end in regions:
        if start <= idx < end:
            return True
    return False


_BLOCK_AMEND_RE = re.compile(
    r'^<span class="amend"([^>]*)>(.*)</span>$', re.DOTALL,
)


def render_body_html(text_with_breaks: str) -> str:
    """Convert the break-tokenised body to HTML paragraphs.

    When a paragraph is purely a single `<span class="amend">…</span>` (i.e.,
    the whole paragraph is one amendment, like an inserted sub-section), tag
    the span with `amend-block` so the CSS can style it as a block. Otherwise
    leave it as an inline highlight.
    """
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
            # The paragraph is exactly one amend span. Promote to block style.
            attrs = m.group(1)
            inner = m.group(2)
            body = f'<span class="amend amend-block"{attrs}>{inner}</span>'
        out_lines.append(f'  <p class="block {cls}">{body}</p>')
    return "<div class=\"statute-body\">\n" + "\n".join(out_lines) + "\n</div>"


def clean_body_text(body: str) -> str:
    """First-pass cleanup before marker replacement and block segmentation."""
    body = re.sub(r"\n[ \t]{4,}", "\n", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    return body


def strip_trailing_section_close_bracket(html_body: str) -> str:
    """If a section was wrapped in `<digit>[ … ]` (whole-section substitution
    or insertion), the closing `]` lands at the very end of the body. Strip it
    cleanly without disturbing other content.
    """
    # Match a stray `]` at the end of the last visible block.
    # Look for `]</p>` at the end of a `<p>` and remove the bracket.
    return re.sub(r"\]\s*</p>\s*</div>\s*$", "</p></div>", html_body)


def format_section_body_per_page(
    chunks: list[tuple[int, str]], amendments: dict
) -> str:
    """Combine per-page text chunks, replace markers per page, then format.

    Markers can span multiple lines, so we group lines by page first and feed
    the entire page's text to the marker replacer in one go.
    """
    pages_grouped: list[tuple[int, list[str]]] = []
    for page_idx, line in chunks:
        if pages_grouped and pages_grouped[-1][0] == page_idx:
            pages_grouped[-1][1].append(line)
        else:
            pages_grouped.append((page_idx, [line]))

    pieces = []
    for page_idx, lines in pages_grouped:
        page_text = "\n".join(lines)
        cleaned = clean_body_text(page_text)
        with_spans = replace_amendment_markers(cleaned, amendments, page_idx)
        pieces.append(with_spans)
    full = "\n".join(pieces)

    # Strip embedded NOTIFICATION blocks. A notification runs from the
    # NOTIFICATION header through the closing "[Vide S.O. ... ]" citation.
    notif_re = re.compile(
        r"\bNOTIFICATION\b\s*(.*?\[Vide\s+[^\]]+\])",
        re.DOTALL,
    )
    notifs: list[str] = []

    def _capture(m: re.Match) -> str:
        notifs.append(m.group(1).strip())
        return " "

    full = notif_re.sub(_capture, full)

    # Strip "COMMENTS (Based on Notes on Clauses of the Bill)" editorial blocks.
    # These are gazette annotations explaining the legislative intent — useful
    # context but not part of the statute text. Everything from the COMMENTS
    # header to the end of the body is dropped.
    comments_re = re.compile(
        r"\bCOMMENTS\b\s*\(Based\s+on\s+Notes\s+on\s+Clauses\s+of\s+the\s+Bill\).*\Z",
        re.DOTALL | re.IGNORECASE,
    )
    full = comments_re.sub("", full).rstrip()

    # Tokenise block breaks then render to HTML.
    tokenised = insert_block_breaks(full)
    html_body = render_body_html(tokenised)

    html_body = strip_trailing_section_close_bracket(html_body)

    if notifs:
        html_body += '\n\n<aside class="notifications">\n  <h3>Related notifications</h3>'
        for n in notifs:
            n = re.sub(r"\s+", " ", n).strip()
            html_body += f'\n  <blockquote>{html.escape(n)}</blockquote>'
        html_body += "\n</aside>"

    return html_body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    text = SRC.read_text()
    pages = text.split("\f")

    sections: list[dict] = []
    current: dict | None = None
    chapter_num: str | None = None
    chapter_title: str | None = None
    saw_chapter_marker = False

    for page_idx, page in enumerate(pages):
        body, footnotes = split_body_and_footnotes(page)
        body_lines = body.split("\n")

        page_amendments: dict[int, dict] = {}
        for num, ftxt in footnotes:
            parsed = parse_amendment_footnote(num, ftxt)
            if parsed:
                page_amendments[num] = parsed

        i = 0
        # Track which body lines belong to which section on this page so we can
        # later attach amendments accurately by inline marker.
        while i < len(body_lines):
            raw_line = body_lines[i]
            line = raw_line.rstrip()

            if is_running_title(line):
                i += 1
                continue

            cm = CHAPTER_RE.match(line)
            if cm:
                chapter_num = cm.group(1)
                chapter_title = None
                saw_chapter_marker = True
                i += 1
                continue
            if saw_chapter_marker and chapter_title is None and line.strip():
                tm = CHAPTER_TITLE_RE.match(line)
                if tm:
                    chapter_title = tm.group(1).title()
                    saw_chapter_marker = False
                    i += 1
                    continue

            sm = SECTION_START_RE.match(line)
            if sm:
                marker_num = sm.group(1)  # str | None
                num = sm.group(2)
                first = sm.group(3).strip()
                if first.startswith(("Subs. by", "Ins. by", "Omitted by")):
                    if current is not None:
                        current["chunks"].append((page_idx, line))
                    i += 1
                    continue

                title_parts = [first]
                j = i
                MAX_WRAP = 3
                wraps = 0
                blanks_seen = 0
                while SECTION_END_TOKEN not in title_parts[-1] and wraps < MAX_WRAP:
                    j += 1
                    wraps += 1
                    if j >= len(body_lines):
                        break
                    nxt_raw = body_lines[j]
                    nxt = nxt_raw.rstrip().strip()
                    if is_running_title(nxt_raw):
                        break
                    if not nxt:
                        if blanks_seen >= 1:
                            break
                        blanks_seen += 1
                        continue
                    if SECTION_START_RE.match(nxt_raw.rstrip()):
                        break
                    title_parts.append(nxt)
                full = " ".join(title_parts).strip()
                if SECTION_END_TOKEN not in full:
                    if current is not None:
                        current["chunks"].append((page_idx, line))
                    i += 1
                    continue
                title, _, body_remainder = full.partition(SECTION_END_TOKEN)
                title = title.strip()
                if len(title) > 140:
                    if current is not None:
                        current["chunks"].append((page_idx, line))
                    i += 1
                    continue
                if current is not None:
                    sections.append(current)
                current = {
                    "section": num,
                    "title": title,
                    "chapter_num": chapter_num,
                    "chapter_title": chapter_title or CHAPTERS.get(chapter_num or "", ""),
                    "chunks": [],  # list of (page_idx, line)
                    "amendments": {},
                    "_page": page_idx,
                    # If the section itself opened with `<digit>[`, that
                    # marker tells us the whole section was substituted /
                    # inserted by the corresponding footnote. We attach the
                    # amendment to the section after parsing footnotes.
                    "_section_marker_page_fnum": (
                        f"p{page_idx}.{int(marker_num)}" if marker_num else None
                    ),
                }
                if body_remainder.strip():
                    current["chunks"].append((page_idx, body_remainder.lstrip()))
                i = j + 1
                continue

            if current is not None:
                current["chunks"].append((page_idx, line))
            i += 1

        # Attach amendments to whichever section's chunks (on this page) contain
        # the matching inline marker. A section's body can span multiple pages,
        # so we look across the full sections list AND the in-flight `current`.
        all_sections = list(sections)
        if current is not None and current not in all_sections:
            all_sections.append(current)
        for fnum, parsed in page_amendments.items():
            marker = f"{fnum}["
            attached = False
            key = f"p{page_idx}.{fnum}"
            # First, attach to any section whose own header was wrapped in
            # this footnote's marker (whole-section substitution/insertion).
            for s in all_sections:
                if s.get("_section_marker_page_fnum") == key:
                    s["amendments"][key] = parsed
                    attached = True
            # Then attach to sections whose page-N body contains the marker.
            for s in all_sections:
                page_text = " ".join(c[1] for c in s.get("chunks", []) if c[0] == page_idx)
                if marker in page_text:
                    s["amendments"][key] = parsed
                    attached = True
            if not attached and current is not None:
                current["amendments"][key] = parsed

    if current is not None:
        sections.append(current)

    # Detect omitted sections from footnote text.
    omitted_re = re.compile(
        r"Section\s+(\d+[A-Z]?),\s+before\s+omission,\s+stood\s+as\s+under:\s*[\"“](.+?)[\"”]",
        re.DOTALL,
    )
    full_text = "\n".join(pages)
    for m in omitted_re.finditer(full_text):
        num = m.group(1)
        omitted_text = re.sub(r"\s+", " ", m.group(2)).strip()
        tm = re.match(r"^(\d+[A-Z]?)\.\s+([^—]+?)\.—(.*)$", omitted_text, re.DOTALL)
        if tm:
            title = tm.group(2).strip()
            body = tm.group(3).strip()
        else:
            title = "Omitted"
            body = omitted_text
        sections.append({
            "section": num,
            "title": title,
            "chapter_num": "VIII",
            "chapter_title": CHAPTERS.get("VIII"),
            "chunks": [(0, body)],
            "amendments": {
                f"omit-{num}": {
                    "kind": "omitted",
                    "by": "2019-amendment-act",
                    "by_text": "Act 14 of 2019",
                    "target": f"section {num}",
                    "date": "2019-07-25",
                    "before": body,
                    "note": f"Section {num} omitted by 2019 Amendment Act.",
                }
            },
            "_omitted": True,
        })

    # Deduplicate. When the same section exists in both body-extracted and
    # footnote-derived "_omitted" form, prefer the _omitted record (it has
    # the verbatim pre-omission text, whereas the body-extracted record only
    # has the "[Repealed]" placeholder).
    seen = set()
    unique: list[dict] = []
    for s in sections:
        key = s["section"]
        if key in seen:
            existing = next(u for u in unique if u["section"] == key)
            replace = False
            if s.get("_omitted") and not existing.get("_omitted"):
                replace = True
            elif (not s.get("_omitted")) and existing.get("_omitted"):
                replace = False
            elif len(s.get("chunks", [])) > len(existing.get("chunks", [])):
                replace = True
            if replace:
                unique.remove(existing)
                unique.append(s)
        else:
            seen.add(key)
            unique.append(s)

    OUT.mkdir(parents=True, exist_ok=True)
    gk = OUT / ".gitkeep"
    if gk.exists():
        gk.unlink()

    # Read existing files to honour `manual_edit: true` frontmatter — those
    # files are preserved verbatim. Hand-edited content survives re-ingest.
    manual_edited: set[str] = set()
    for p in OUT.glob("s-*.md"):
        try:
            head = p.read_text().split("---", 2)
            if len(head) >= 2 and re.search(r"^\s*manual_edit\s*:\s*true\s*$", head[1], re.MULTILINE):
                manual_edited.add(p.name)
        except OSError:
            pass

    for s in unique:
        # Determine status.
        amendments = list(s["amendments"].values())
        has_inserted = any(a["kind"] == "inserted" for a in amendments)
        has_subs = any(a["kind"] == "substituted" for a in amendments)
        has_omit = any(a["kind"] == "omitted" for a in amendments)
        if s.get("_omitted"):
            status = "omitted"
        elif re.match(r"^\d+[A-Z]+$", s["section"]):
            status = "inserted"
        elif has_inserted or has_subs or has_omit:
            status = "amended"
        else:
            status = "original"

        # Format body as HTML.
        if s.get("_omitted"):
            # Body is the pre-omission text — flag wrapper for timeline mode.
            cleaned = clean_body_text(s["chunks"][0][1] if s["chunks"] else "")
            tokenised = insert_block_breaks(cleaned)
            inner = render_body_html(tokenised)
            body_html = (
                '<div class="omitted-notice">This section was omitted by the '
                '<a href="/amendments/2019-amendment-act">Aadhaar and Other Laws '
                '(Amendment) Act, 2019</a> on 25 July 2019. The text below shows '
                'the section as it stood before omission.</div>\n' + inner
            )
        else:
            body_html = format_section_body_per_page(s["chunks"], s["amendments"])

        # Build history (always include enactment as anchor).
        history_lines = [
            "  - date: 2016-03-25\n    by: original\n    kind: enacted"
        ]
        for a in amendments:
            entry = ["  - date: " + a["date"]]
            entry.append(f"    by: {a['by']}")
            entry.append(f"    kind: {a['kind']}")
            if a.get("target"):
                target = a["target"].replace('"', '\\"')
                entry.append(f'    target: "{target}"')
            if a.get("note"):
                note = a["note"].replace('"', '\\"').replace("\n", " ")
                entry.append(f'    note: "{note}"')
            if a.get("before"):
                bb = a["before"].replace("\n", " ").strip()
                bb = bb.replace("\\", "\\\\").replace('"', '\\"')
                entry.append(f'    before: "{bb}"')
            history_lines.append("\n".join(entry))

        chapter_label = ""
        if s["chapter_num"]:
            ct = CHAPTERS.get(s["chapter_num"], s["chapter_title"] or "")
            chapter_label = f"{s['chapter_num']} — {ct}"

        title = s["title"].replace('"', '\\"')
        fm_lines = [
            "---",
            f'section: "{s["section"]}"',
            f'title: "{title}"',
        ]
        if chapter_label:
            fm_lines.append(f'chapter: "{chapter_label}"')
            order = CHAPTER_ORDER.get(s["chapter_num"] or "", 99)
            fm_lines.append(f"chapter_order: {order}")
        fm_lines.append(f"status: {status}")
        fm_lines.append("current_as_of: 2023-10-10")
        fm_lines.append("history:")
        fm_lines.extend(history_lines)
        fm_lines.append("---")
        fm_lines.append("")

        out_path = OUT / f"s-{s['section'].lower()}.md"
        if out_path.name in manual_edited:
            print(f"  skipped {out_path.name} (manual_edit: true)")
            continue
        out_path.write_text("\n".join(fm_lines) + body_html + "\n")
        print(f"  wrote {out_path.name} ({s['section']} — {s['title']})")

    print(f"\nTotal sections written: {len(unique)}")


if __name__ == "__main__":
    main()
