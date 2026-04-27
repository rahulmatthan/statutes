"""Parse each base UIDAI regulation PDF into structured markdown.

For each instrument, we extract every regulation (1, 2, 3 …) with its
sub-regulations, clauses, and inline amendment markers, and write a single
markdown file at src/content/regulations/<slug>.md whose body is HTML formatted
the same way as Act sections.

Footnote conventions are different from the Act:
    "Subs. for 'X' vide Notification No. Y, dated <date>"
    "Inserted by Notification No. Y, dated <date>"
    "Omitted by Notification No. Y, dated <date>"

We map the footnote's notification date (w.e.f. preferred) to the corresponding
amendment file in src/content/regulation-amendments/<parent>/<YYYY-MM-DD>.md
when one exists, so amendment popovers can link back to the amending instrument.

Files with `manual_edit: true` in their frontmatter are preserved.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib_parse import (
    BREAK_TOKEN,
    clean_body_text,
    insert_block_breaks,
    is_manual_edit,
    render_body_html,
    replace_amendment_markers,
    strip_trailing_section_close_bracket,
)


# ---------------------------------------------------------------------------
# Per-instrument config: slug, title, sections used, gazette date, PDF URL,
# extracted-text filename. Same list as the previous skeleton generator.
# ---------------------------------------------------------------------------

# (slug, title, made_under_sections, gazette_date, current_pdf_url, txt_filename,
#  original_pdf_url [Wayback], original_as_of [date])
BASE_REGULATIONS = [
    (
        "enrolment-and-update-2016",
        "Aadhaar (Enrolment and Update) Regulations, 2016",
        ["3", "23(2)(g)", "23(2)(h)", "23(2)(i)", "23(2)(j)",
         "54(2)(a)", "54(2)(b)", "54(2)(c)", "54(2)(d)", "54(2)(e)"],
        "2016-09-12",
        "https://uidai.gov.in/images/Aadhaar_Enrolment_and_Update_Regulations_2016.pdf",
        "reg-enrolment-and-update-2016.txt",
        # As-enacted text — from the 2016 compendium (Wayback snapshot of UIDAI's
        # original publication PDF, captured 22 Sep 2017, contains regs 1–5 of 2016).
        "https://web.archive.org/web/20170922170843id_/https://uidai.gov.in/images/regulation_1_to_5_15092016.pdf",
        "2016-09-12",
    ),
    (
        "authentication-and-offline-verification-2021",
        "Aadhaar (Authentication and Offline Verification) Regulations, 2021",
        ["8", "8A", "23(2)(p)", "23A", "54(2)(t)"],
        "2021-11-08",
        "https://uidai.gov.in/images/The_Aadhaar_Authentication_and_Offline_Verifications_Regulations_2021-_Clean_copy-30122025.pdf",
        "reg-authentication-and-offline-verification-2021.txt",
        # Earliest Wayback snapshot (Jan 2022) — pre-amendment.
        "https://web.archive.org/web/20220101090006id_/https://uidai.gov.in/images/Aadhaar_Authentication_and_Offline_Verification_Regulations_2021.pdf",
        "2021-11-08",
    ),
    (
        "sharing-of-information-2016",
        "Aadhaar (Sharing of Information) Regulations, 2016",
        ["29", "54(2)(s)"],
        "2016-09-12",
        "https://uidai.gov.in/images/The_Aadhaar_Sharing_of_information_regulation_2016.pdf",
        "reg-sharing-of-information-2016.txt",
        "https://web.archive.org/web/20170922170843id_/https://uidai.gov.in/images/regulation_1_to_5_15092016.pdf",
        "2016-09-12",
    ),
    (
        "data-security-2016",
        "Aadhaar (Data Security) Regulations, 2016",
        ["28", "54(2)(r)"],
        "2016-09-12",
        "https://uidai.gov.in/images/The_Aadhaar_Data_Security_Regulations_2016.pdf",
        "reg-data-security-2016.txt",
        "https://web.archive.org/web/20170922170843id_/https://uidai.gov.in/images/regulation_1_to_5_15092016.pdf",
        "2016-09-12",
    ),
    (
        "payment-of-fees-2023",
        "The Aadhaar (Payment of Fees for Performance of Authentication) Regulations, 2023",
        ["8(4)", "54(2)"],
        "2023-12-22",
        "https://uidai.gov.in/images/The_Aadhaar_payment_of_fees_for_performance_of_Authentication_Regulations_2023.pdf",
        "reg-payment-of-fees-2023.txt",
        # No usable pre-amendment snapshot exists — the earliest Wayback copy
        # (June 2024) already includes the 2024-01-31 amendment, so we don't
        # claim it as "as-enacted". Pages will surface the gap in the UI.
        None,
        None,
    ),
    (
        "transaction-of-business-2016",
        "Unique Identification Authority of India (Transaction of Business at Meetings of the Authority) Regulations, 2016",
        ["19", "54(2)(g)"],
        "2016-09-12",
        "https://uidai.gov.in/images/1_The_Unique_Identification_Authority_of_India_Transaction_of_Business_at_Meetings_of_the_Authority_Regulations_2016.pdf",
        "reg-transaction-of-business-2016.txt",
        "https://web.archive.org/web/20170922170843id_/https://uidai.gov.in/images/regulation_1_to_5_15092016.pdf",
        "2016-09-12",
    ),
    (
        "appointment-of-officers-2020",
        "Unique Identification Authority of India (Appointment of Officers and Employees) Regulations, 2020",
        ["21(1)", "54(2)(h)"],
        "2020-08-06",
        "https://uidai.gov.in/images/THE_UNIQUE_IDENTIFICATION_AUTHORITY_OF_INDIA_APPOINTMENT_OF_OFFICERS_AND_EMPLOYEES_REGULATIONS_2020.pdf",
        "reg-appointment-of-officers-2020.txt",
        # Wayback snapshot from Aug 2022 — pre-2024 amendment.
        "https://web.archive.org/web/20220808075206id_/https://uidai.gov.in/images/10_Appointment_of_Officers_Employees_of_UIDAI.pdf",
        "2020-08-06",
    ),
    (
        "salary-allowances-2020",
        "Unique Identification Authority of India (Salary, Allowances and other Terms and Conditions of Service of Employees) Regulations, 2020",
        ["21(2)", "54(2)(h)"],
        "2020-08-06",
        "https://uidai.gov.in/images/THE_UNIQUE_IDENTIFICATION_AUTHORITY_OF_INDIA_SALARY_ALLOWANCES_AND_OTHER_TERMS_AND_CONDITIONS_OF_SERVICE_OF_EMPLOYEES_REGULATIONS_2020.pdf",
        "reg-salary-allowances-2020.txt",
        "https://web.archive.org/web/20220806043545id_/https://uidai.gov.in/images/11_Salary_Allowance_of_Employee_of_UIDAI.pdf",
        "2020-08-06",
    ),
]


# ---------------------------------------------------------------------------
# Gazette-style headers
# ---------------------------------------------------------------------------

CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVX]+[A-Z]*)\s*$")
CHAPTER_TITLE_RE = re.compile(r"^\s*([A-Z][A-Z, ]+[A-Z])\s*$")
ITEM_START_RE = re.compile(r"^\s*(?:(\d+)\[)?(\d+[A-Z]?)\.\s+([A-Za-z\[].*)$")
# The "title.—body" separator may be em-dash, en-dash, hyphen, or any of those
# preceded by a stray space introduced by pdftotext.
ITEM_END_TOKEN_DEFAULTS = (".—", ". —", ".–", ". –", ".‒", ". ‒", ".-", ". -")
# Backward-compatible aliases retained for callers that import these names.
ITEM_END_TOKEN = ".—"
ITEM_END_TOKEN_ALT = ". —"

FOOTNOTE_LINE_RE = re.compile(r"^\s{0,8}(\d{1,3})\.?\s+[A-Z]")
FOOTNOTE_AMEND_RE = re.compile(
    r"^\s{0,8}(\d{1,3})\s*\.?\s+(?:Ins(?:erted)?|Subs(?:tituted)?\b|Omitted\b|"
    r"Sub[- ]?regulations?\b|Sub[- ]?clause\b|Vide\b|Published\s+in|"
    r"Notified\s+vide|Came\s+into\s+force)",
    re.IGNORECASE,
)

# Footnote number indicators may also appear as superscripts in the body of
# the page — we already strip them using FOOTNOTE_LINE_RE.

NOTIFICATION_DATE_RE = re.compile(
    # Allow optional whitespace between the day and its st/nd/rd/th suffix
    # (pdftotext sometimes splits "20th" into "20 th").
    r"(?:dated\s+(?P<dated>\d{1,2}\s*(?:st|nd|rd|th)?[\s,-]+[A-Za-z]+[,\s]+\d{4}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}-\d{1,2}-\d{4}))"
    r"|(?:w\.e\.f\.\s*(?P<wef>\d{1,2}\s*(?:st|nd|rd|th)?[\s,\.\-]+[A-Za-z]+[,\s]+\d{4}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}-\d{1,2}-\d{4}))"
)

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def normalise_date(raw: str) -> str | None:
    """Return YYYY-MM-DD or None."""
    raw = raw.strip().rstrip(",.")
    # 25.01.2024 / 25-01-2024
    m = re.match(r"^(\d{1,2})[\.\-](\d{1,2})[\.\-](\d{4})$", raw)
    if m:
        d, mn, y = m.groups()
        return f"{y}-{int(mn):02d}-{int(d):02d}"
    # 25th January, 2024 / 25 January 2024 / 25 th August, 2025 / 25th January 2024
    # — allow whitespace between the day digits and the st/nd/rd/th suffix.
    m = re.match(
        r"^(\d{1,2})\s*(?:st|nd|rd|th)?[\s\.-]+([A-Za-z]+)[,\s]+(\d{4})$",
        raw,
    )
    if m:
        d, mn_name, y = m.groups()
        mn = MONTHS.get(mn_name.lower())
        if mn:
            return f"{y}-{mn:02d}-{int(d):02d}"
    return None


def extract_footnote_dates(text: str) -> list[str]:
    """Return all dated/w.e.f. dates appearing in a footnote text, normalised."""
    dates: list[str] = []
    for m in NOTIFICATION_DATE_RE.finditer(text):
        for group in ("wef", "dated"):
            v = m.group(group)
            if v:
                d = normalise_date(v)
                if d:
                    dates.append(d)
    return dates


def parse_regulation_footnote(num: int, text: str, parent_slug: str,
                              amendment_dates: set[str]) -> dict | None:
    """Parse a regulation-style footnote into an amendment record."""
    t = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()

    if re.match(r"^Ins(?:erted)?\b", t, re.IGNORECASE):
        kind = "inserted"
    elif re.match(r"^Subs(?:tituted)?\b", t, re.IGNORECASE):
        kind = "substituted"
    elif re.match(r"^Omitted\b", t, re.IGNORECASE):
        kind = "omitted"
    else:
        return None

    # Extract before-text from "Subs. for 'X'" or "Subs. for the words 'X'".
    before = None
    if kind == "substituted":
        bm = re.search(r"for\s+(?:the\s+(?:words?|expressions?|figures?(?:\s+and\s+letters)?|brackets?\s+(?:and|or)\s+(?:words?|figures?))\s+)?[\"'“]([^\"'”]+)[\"'”]", t)
        if bm:
            before = bm.group(1).strip()
        # Also handle "stood as under: 'X'"
        if not before:
            bm = re.search(r"stood\s+as\s+under:\s*[\"'“](.+?)[\"'”]\s*\.?$", t, re.DOTALL)
            if bm:
                before = re.sub(r"\s+", " ", bm.group(1)).strip()

    # Extract date(s).
    dates = extract_footnote_dates(t)
    matched_date = None
    for d in dates:
        if d in amendment_dates:
            matched_date = d
            break
    # Fallback: use the latest extracted date if any.
    date = matched_date or (dates[-1] if dates else "")

    # Build a "by" slug. If we know the matching amendment in our content,
    # use `<parent>/<date>` so the popover can link to it.
    if matched_date:
        by_slug = f"{parent_slug}/{matched_date}"
    else:
        by_slug = "unknown"

    # by_text: short summary of the amending instrument.
    by_text_match = re.search(
        r"(?:Notification\s+No\.\s+[^\s,]+|F\.?\s*No\.\s+[^\s,]+)", t,
    )
    by_text = by_text_match.group(0) if by_text_match else ""

    note = None
    if kind == "inserted":
        note = "Inserted by amendment regulations"
    elif kind == "substituted":
        note = "Substituted by amendment regulations"
    elif kind == "omitted":
        note = "Omitted by amendment regulations"

    return {
        "footnote": num,
        "kind": kind,
        "by": by_slug,
        "by_text": by_text,
        "target": None,
        "date": date,
        "before": before,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Body / footnote splitter
# ---------------------------------------------------------------------------

def is_running_title(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # Common headers in regulation gazette pages.
    if re.search(r"\bGAZETTE\s+OF\s+INDIA\b", line, re.IGNORECASE):
        return True
    if re.search(r"^\s*\d+\s*$", line):
        return True
    if "[PART II" in line:
        return True
    return False


# Patterns describing what a real FOOTNOTE content line looks like — used to
# decide whether to merge a `\nN\nindented…` block. We only merge when the
# next line is recognisably a footnote (Subs./Ins./Omitted by …, Notified
# vide …, "stood as under" continuations).
_FOOTNOTE_CONTENT_RE = re.compile(
    r"^\s+(?:Subs(?:tituted)?\b|Ins(?:erted)?\b|Omitted\b|Notified\b|"
    r"Came\s+into\s+force\b|The\s+(?:words?|word|expression|figures?)\b|"
    r"Inserted\b|Substituted\b|For\s+the\s+(?:words?|expression)\b|"
    r"Sub[- ]?regulations?\b|Sub[- ]?clause\b|Clause\s+\([a-z]\)|"
    r"Section\s+\d+|Vide\b|Published\s+in)",
    re.IGNORECASE,
)


def normalise_multi_line_footnotes(page: str) -> str:
    """Some regulation PDFs put the footnote number on its own line:

        3
           Subs. for "a resident" vide Notification No. ...

    Merge those into the single-line form expected by the splitter:

        3. Subs. for "a resident" vide Notification No. ...

    We only merge when the next line is *recognisably* footnote content; in
    particular we do NOT merge when the next line starts with a regulation
    header like "4. [Demographic information.—…" (a body marker `12[` whose
    bracket landed in front of a regulation number).
    """
    lines = page.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^\s*(\d{1,3})\s*$", line)
        if m and i + 1 < len(lines):
            nxt = lines[i + 1]
            # Skip if next line looks like a regulation/rule heading.
            if re.match(r"^\s*(?:\d+[A-Z]?)\.\s+\S", nxt):
                out.append(line)
                i += 1
                continue
            # Only merge when the next line looks like footnote content.
            if _FOOTNOTE_CONTENT_RE.match(nxt):
                merged = f"  {m.group(1)}. {nxt.lstrip()}"
                out.append(merged)
                i += 2
                while i < len(lines):
                    cont = lines[i]
                    if re.match(r"^\s*\d{1,3}\s*$", cont):
                        break
                    if not cont.strip():
                        out.append(cont)
                        i += 1
                        continue
                    if re.match(r"^\s+\S", cont):
                        out.append(cont)
                        i += 1
                        continue
                    break
                continue
        out.append(line)
        i += 1
    return "\n".join(out)


def split_body_and_footnotes(page: str) -> tuple[str, list[tuple[int, str]]]:
    page = normalise_multi_line_footnotes(page)
    lines = page.split("\n")

    candidates: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = FOOTNOTE_LINE_RE.match(line)
        if m:
            candidates.append((i, int(m.group(1))))

    foot_start = None
    # First, look for any line that's distinctively an amendment footnote.
    for idx, (li, num) in enumerate(candidates):
        if any(t in lines[li] for t in ITEM_END_TOKEN_DEFAULTS):
            continue
        if FOOTNOTE_AMEND_RE.match(lines[li]):
            foot_start = li
            break
    # If none, fall back to the "1. ... 2. ..." consecutive-number heuristic.
    if foot_start is None:
        for idx, (li, num) in enumerate(candidates):
            if num != 1:
                continue
            if any(t in lines[li] for t in ITEM_END_TOKEN_DEFAULTS):
                continue
            for li2, num2 in candidates[idx + 1: idx + 12]:
                if num2 == 2 and li2 - li <= 35:
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
        m = FOOTNOTE_LINE_RE.match(line)
        if m and len(m.group(1)) <= 3:
            if cur_num is not None:
                footers.append((cur_num, "\n".join(cur_buf).strip()))
            cur_num = int(m.group(1))
            rest = re.match(r"^\s{0,8}\d+\s*\.?\s+(.+)$", line)
            cur_buf = [rest.group(1).rstrip()] if rest else []
        else:
            if cur_num is not None:
                cur_buf.append(line.rstrip())
    if cur_num is not None:
        footers.append((cur_num, "\n".join(cur_buf).strip()))
    return body, footers


# ---------------------------------------------------------------------------
# Document parsing — same shape as parse_act, but per-document
# ---------------------------------------------------------------------------

# Appendix headings are centred on their line (long leading whitespace) and
# typed in a distinctive style: "Form A" / "FORM A" / "Schedule 1" / "APPENDIX-I"
# alone on the line, optionally followed by "[See rule N]". Inline references
# like "Schedule I" inside body text don't have the centring whitespace.
_APPENDIX_HEADING_RE = re.compile(
    r"^[ \t]{8,}(?:Form\s+[A-Z]|FORM\s+[A-Z]|Schedule\s+\d+|"
    r"SCHEDULE\s+\d+|APPENDIX[\s\-]+[IVX0-9]+|Appendix[\s\-]+[IVX0-9]+)\s*$",
    re.MULTILINE,
)


def strip_trailing_appendices(text: str) -> str:
    """Remove the trailing form/schedule/appendix block from the body.

    Cuts at the FIRST line that looks like a centred appendix heading.
    Inline cross-references ("see Schedule I") don't have the leading
    whitespace and are left alone.
    """
    m = _APPENDIX_HEADING_RE.search(text)
    if not m:
        return text
    return text[: m.start()].rstrip()


def parse_document(text: str, parent_slug: str,
                   amendment_dates: set[str]) -> list[dict]:
    text = strip_trailing_appendices(text)
    pages = text.split("\f")

    items: list[dict] = []
    current: dict | None = None
    chapter_num: str | None = None
    chapter_title: str | None = None
    saw_chapter = False
    pending_marker: int | None = None  # standalone "<digit>" preceding an item header

    for page_idx, page in enumerate(pages):
        body, footnotes = split_body_and_footnotes(page)
        body_lines = body.split("\n")

        page_amendments: dict[int, dict] = {}
        for num, ftxt in footnotes:
            parsed = parse_regulation_footnote(
                num, ftxt, parent_slug, amendment_dates,
            )
            if parsed:
                page_amendments[num] = parsed

        i = 0
        while i < len(body_lines):
            line = body_lines[i].rstrip()

            # Standalone marker number (body-level whole-item marker like
            # `12\n  4. [Demographic information…`). Check this BEFORE the
            # running-title filter, which would otherwise swallow it as a
            # page-number artefact.
            stand_m = re.match(r"^\s*(\d{1,3})\s*$", line)
            if stand_m and i + 1 < len(body_lines):
                nxt = body_lines[i + 1].rstrip()
                if ITEM_START_RE.match(nxt):
                    pending_marker = int(stand_m.group(1))
                    i += 1
                    continue

            if is_running_title(line):
                i += 1
                continue

            cm = CHAPTER_RE.match(line)
            if cm:
                chapter_num = cm.group(1)
                chapter_title = None
                saw_chapter = True
                pending_marker = None
                i += 1
                continue
            if saw_chapter and chapter_title is None and line.strip():
                tm = CHAPTER_TITLE_RE.match(line)
                if tm:
                    chapter_title = tm.group(1).title()
                    saw_chapter = False
                    i += 1
                    continue

            sm = ITEM_START_RE.match(line)
            if sm:
                marker_num = sm.group(1) or (str(pending_marker) if pending_marker else None)
                pending_marker = None
                num = sm.group(2)
                first = sm.group(3).strip()
                if first.startswith(("Subs.", "Ins.", "Omitted")):
                    if current is not None:
                        current["chunks"].append((page_idx, line))
                    i += 1
                    continue
                # Accept either ".—" or ". —"
                title_parts = [first]
                j = i
                MAX_WRAP = 3
                wraps = 0
                blanks = 0
                end_token = None
                while wraps < MAX_WRAP:
                    joined = " ".join(title_parts)
                    end_token = next(
                        (t for t in ITEM_END_TOKEN_DEFAULTS if t in joined),
                        None,
                    )
                    if end_token:
                        break
                    j += 1
                    wraps += 1
                    if j >= len(body_lines):
                        break
                    nx = body_lines[j].rstrip().strip()
                    if is_running_title(body_lines[j]):
                        break
                    if not nx:
                        if blanks >= 1:
                            break
                        blanks += 1
                        continue
                    if ITEM_START_RE.match(body_lines[j].rstrip()):
                        break
                    title_parts.append(nx)
                full = " ".join(title_parts).strip()
                if not end_token:
                    if current is not None:
                        current["chunks"].append((page_idx, line))
                    i += 1
                    continue
                title, _, rem = full.partition(end_token)
                title = title.strip()
                # When a regulation/rule was substituted as a whole, the
                # consolidated PDF wraps the entire item in `N[…]`. The opening
                # bracket lands at the start of the title (e.g., "[Demographic
                # information"). Strip it; the corresponding `]` at the body's
                # end is removed by strip_trailing_section_close_bracket().
                title = title.lstrip("[").strip()
                if len(title) > 160:
                    if current is not None:
                        current["chunks"].append((page_idx, line))
                    i += 1
                    continue
                if current is not None:
                    items.append(current)
                current = {
                    "number": num,
                    "title": title,
                    "chapter_num": chapter_num,
                    "chapter_title": chapter_title,
                    "chunks": [],
                    "amendments": {},
                    "_page": page_idx,
                    "_section_marker_page_fnum": (
                        f"p{page_idx}.{int(marker_num)}" if marker_num else None
                    ),
                }
                if rem.strip():
                    current["chunks"].append((page_idx, rem.lstrip()))
                i = j + 1
                continue

            if current is not None:
                current["chunks"].append((page_idx, line))
            i += 1

        # Attach amendments to items containing the marker on this page.
        all_items = list(items)
        if current is not None and current not in all_items:
            all_items.append(current)
        for fnum, parsed in page_amendments.items():
            marker = f"{fnum}["
            key = f"p{page_idx}.{fnum}"
            attached = False
            for it in all_items:
                if it.get("_section_marker_page_fnum") == key:
                    it["amendments"][key] = parsed
                    attached = True
            for it in all_items:
                page_text = " ".join(
                    c[1] for c in it.get("chunks", []) if c[0] == page_idx
                )
                if marker in page_text:
                    it["amendments"][key] = parsed
                    attached = True
            if not attached and current is not None:
                current["amendments"][key] = parsed

    if current is not None:
        items.append(current)
    return items


# ---------------------------------------------------------------------------
# Per-item body rendering
# ---------------------------------------------------------------------------

def render_item_body(item: dict) -> str:
    """Render one item's body as `<div class="statute-body">…</div>`.

    The heading lives in the page template (driven by frontmatter), so we
    return only the prose body here.
    """
    pages_grouped: list[tuple[int, list[str]]] = []
    for page_idx, line in item["chunks"]:
        if pages_grouped and pages_grouped[-1][0] == page_idx:
            pages_grouped[-1][1].append(line)
        else:
            pages_grouped.append((page_idx, [line]))

    pieces = []
    for page_idx, lines in pages_grouped:
        text = "\n".join(lines)
        text = clean_body_text(text)
        text = replace_amendment_markers(text, item["amendments"], page_idx)
        pieces.append(text)
    body_text = "\n".join(pieces).strip()

    tokenised = insert_block_breaks(body_text)
    body_html = render_body_html(tokenised)
    return strip_trailing_section_close_bracket(body_html)


def derive_item_status(item: dict) -> str:
    amendments = item.get("amendments", {})
    # If the item header was wrapped in `N[...]` (whole-item amendment
    # marker), use that to distinguish a wholly-inserted vs. wholly-
    # substituted regulation. A plain "inserted" record on a numeric item
    # means the entire item was added later.
    section_marker = item.get("_section_marker_page_fnum")
    if section_marker and section_marker in amendments:
        kind = amendments[section_marker]["kind"]
        if kind == "inserted":
            return "inserted"
        if kind == "substituted":
            return "amended"
    has_inserted = any(a["kind"] == "inserted" for a in amendments.values())
    has_subs = any(a["kind"] == "substituted" for a in amendments.values())
    has_omit = any(a["kind"] == "omitted" for a in amendments.values())
    if re.match(r"^\d+[A-Z]+$", item["number"]):
        return "inserted"
    if has_inserted or has_subs or has_omit:
        return "amended"
    return "original"


def build_history_yaml(item: dict, gazette_date: str) -> list[str]:
    """Build the YAML `history:` array for an item.

    Skips amendments without a parseable date (we'd rather omit a record
    than misattribute it to the gazette date), and dedupes entries that have
    the same (date, by, kind) since an amendment block can be referenced
    multiple times in a single regulation's body.
    """
    out = [f"  - date: {gazette_date}\n    by: original\n    kind: enacted"]
    seen: set[tuple[str, str, str]] = set()
    for a in item["amendments"].values():
        date = a.get("date") or ""
        if not date:
            continue
        by = a.get("by") or "unknown"
        if by == "unknown":
            continue
        key = (date, by, a["kind"])
        if key in seen:
            continue
        seen.add(key)
        entry = ["  - date: " + date]
        entry.append(f"    by: {by}")
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
        out.append("\n".join(entry))
    return out


def write_item_file(items_dir: Path, parent_slug: str, item: dict,
                    gazette_date: str) -> tuple[bool, str]:
    """Write one regulation/rule to its own .md file. Returns (written, name)."""
    num = item["number"]
    item_path = items_dir / f"{num.lower()}.md"
    if is_manual_edit(item_path):
        return (False, item_path.name)

    body_html = render_item_body(item)
    status = derive_item_status(item)
    history = build_history_yaml(item, gazette_date)

    chapter_label = ""
    if item["chapter_num"]:
        chapter_label = item["chapter_num"]
        if item.get("chapter_title"):
            chapter_label = f"{item['chapter_num']} — {item['chapter_title']}"

    title_escape = item["title"].replace('"', '\\"')

    fm = [
        "---",
        f"parent: {parent_slug}",
        f'number: "{num}"',
        f'title: "{title_escape}"',
    ]
    if chapter_label:
        fm.append(f'chapter: "{chapter_label}"')
    fm.append(f"status: {status}")
    fm.append("history:")
    fm.extend(history)
    fm.append("---")
    fm.append("")

    item_path.write_text("\n".join(fm) + body_html + "\n")
    return (True, item_path.name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect_amendment_dates(parent_slug: str) -> set[str]:
    """Return YYYY-MM-DD dates of amendments registered for this parent."""
    folder = ROOT / "src/content/regulation-amendments" / parent_slug
    if not folder.exists():
        return set()
    return {p.stem for p in folder.glob("*.md")}


# ---------------------------------------------------------------------------
# Originals (as-enacted) parser — slices the 2016 compendium into its
# component regulations and parses each independently. Single-regulation
# original PDFs are parsed straight through.
# ---------------------------------------------------------------------------

# Each entry: (set_slug, original_text_filename, slice_start_pattern, slice_end_pattern_or_None)
# A None end pattern means "until end of file".
ORIGINAL_SOURCES = [
    # 2016 compendium — covers four sets. Pattern matches the heading line
    # (with the typo "REGUALTIONS" in Enrolment & Update preserved).
    (
        "transaction-of-business-2016",
        "orig-2016-compendium.txt",
        r"^.*UNIQUE\s+IDENTIFICATION\s+AUTHORITY\s+OF\s+INDIA\s+\(TRANSACTION\s+OF\s+BUSINESS",
        r"^.*AADHAAR\s+\(ENROLMENT\s+AND\s+UPDATE\)\s+REGUALTIONS,\s+2016",
    ),
    (
        "enrolment-and-update-2016",
        "orig-2016-compendium.txt",
        r"^.*AADHAAR\s+\(ENROLMENT\s+AND\s+UPDATE\)\s+REGUALTIONS,\s+2016",
        r"^.*AADHAAR\s+\(AUTHENTICATION\)\s+REGULATIONS,\s+2016",
    ),
    # Authentication 2016 is skipped: it was wholly replaced by the 2021
    # Authentication and Offline Verification Regulations.
    (
        "data-security-2016",
        "orig-2016-compendium.txt",
        r"^.*AADHAAR\s+\(DATA\s+SECURITY\)\s+REGULATIONS,\s+2016",
        r"^.*AADHAAR\s+\(SHARING\s+OF\s+INFORMATION\)\s+REGULATIONS,\s+2016",
    ),
    (
        "sharing-of-information-2016",
        "orig-2016-compendium.txt",
        r"^.*AADHAAR\s+\(SHARING\s+OF\s+INFORMATION\)\s+REGULATIONS,\s+2016",
        None,
    ),
    # Single-PDF originals — parse the whole file.
    (
        "authentication-and-offline-verification-2021",
        "orig-authentication-and-offline-verification-2021-original.txt",
        None,
        None,
    ),
    (
        "appointment-of-officers-2020",
        "orig-appointment-of-officers-2020-original.txt",
        None,
        None,
    ),
    (
        "salary-allowances-2020",
        "orig-salary-allowances-2020-original.txt",
        None,
        None,
    ),
    # Payment of Fees 2023 — no genuine pre-amendment snapshot exists. The
    # 2024-06 snapshot is post-first-amendment; treating it as "as enacted"
    # was misleading users. Skip it.
]


def _slice_text(full_text: str, start_re: str | None, end_re: str | None) -> str:
    if not start_re and not end_re:
        return full_text
    start = 0
    end = len(full_text)
    if start_re:
        m = re.search(start_re, full_text, re.MULTILINE | re.IGNORECASE)
        if m:
            start = m.start()
    if end_re:
        m = re.search(end_re, full_text, re.MULTILINE | re.IGNORECASE)
        if m and m.start() > start:
            end = m.start()
    return full_text[start:end]


def write_original_item_file(items_dir: Path, parent_slug: str, item: dict,
                             gazette_date: str) -> tuple[bool, str]:
    """Write one as-enacted regulation/rule to its own file under
    `regulation-items-original/<set>/<num>.md`. Same shape as the current
    parser but no `history` array (this IS the as-enacted snapshot).
    """
    num = item["number"]
    item_path = items_dir / f"{num.lower()}.md"
    if is_manual_edit(item_path):
        return (False, item_path.name)

    # The original text shouldn't have inline amendment markers (it pre-dates
    # all amendments), but the consolidated PDF format may still surround it
    # in `1[…]` markers from gazette typography. Strip them by clearing the
    # amendments dict so marker replacement leaves the brackets as text.
    clean_item = dict(item)
    clean_item["amendments"] = {}
    body_html = render_item_body(clean_item)

    chapter_label = ""
    if item["chapter_num"]:
        chapter_label = item["chapter_num"]
        if item.get("chapter_title"):
            chapter_label = f"{item['chapter_num']} — {item['chapter_title']}"

    title_escape = item["title"].replace('"', '\\"')

    fm = [
        "---",
        f"parent: {parent_slug}",
        f'number: "{num}"',
        f'title: "{title_escape}"',
    ]
    if chapter_label:
        fm.append(f'chapter: "{chapter_label}"')
    fm.append(f"as_of: {gazette_date}")
    fm.append("---")
    fm.append("")

    item_path.write_text("\n".join(fm) + body_html + "\n")
    return (True, item_path.name)


def parse_originals() -> tuple[int, int]:
    """Parse each archived as-enacted PDF into per-item files."""
    out_root = ROOT / "src/content/regulation-items-original"
    out_root.mkdir(parents=True, exist_ok=True)
    extracted_dir = ROOT / "source-pdfs/extracted"

    # Map: slug → gazette_date (taken from BASE_REGULATIONS for parent set).
    gazette_by_slug = {row[0]: row[3] for row in BASE_REGULATIONS}

    written = skipped = 0
    for slug, txt_filename, start_re, end_re in ORIGINAL_SOURCES:
        text_path = extracted_dir / txt_filename
        if not text_path.exists():
            print(f"  WARNING: {txt_filename} missing — run pdftotext first")
            continue
        full_text = text_path.read_text()
        sliced = _slice_text(full_text, start_re, end_re)

        items = parse_document(sliced, slug, set())
        items_dir = out_root / slug
        items_dir.mkdir(parents=True, exist_ok=True)
        seen = set()
        for item in items:
            if item["number"] in seen:
                continue
            seen.add(item["number"])
            wrote, name = write_original_item_file(
                items_dir, slug, item, gazette_by_slug.get(slug, "2016-01-01"),
            )
            if wrote:
                written += 1
            else:
                print(f"  skipped original {slug}/{name} (manual_edit: true)")
                skipped += 1
        print(f"  {slug}: {len(seen)} as-enacted regulations")
    return written, skipped


def main() -> None:
    out_set_dir = ROOT / "src/content/regulations"
    out_items_root = ROOT / "src/content/regulation-items"
    out_set_dir.mkdir(parents=True, exist_ok=True)
    out_items_root.mkdir(parents=True, exist_ok=True)
    extracted_dir = ROOT / "source-pdfs/extracted"

    sets_written = sets_skipped = 0
    items_written = items_skipped = 0

    for entry in BASE_REGULATIONS:
        (slug, title, sections, gazette_date, pdf_url, txt_filename,
         original_pdf_url, original_as_of) = entry
        amendment_dates = collect_amendment_dates(slug)
        text = (extracted_dir / txt_filename).read_text()
        items = parse_document(text, slug, amendment_dates)

        items_dir = out_items_root / slug
        items_dir.mkdir(parents=True, exist_ok=True)

        # Write each item.
        seen_nums = set()
        for item in items:
            if item["number"] in seen_nums:
                continue  # dedupe within a document
            seen_nums.add(item["number"])
            written, name = write_item_file(items_dir, slug, item, gazette_date)
            if written:
                items_written += 1
            else:
                print(f"  skipped {slug}/{name} (manual_edit: true)")
                items_skipped += 1

        # Write set-level slim file (overview only, no body).
        set_path = out_set_dir / f"{slug}.md"
        if is_manual_edit(set_path):
            print(f"  skipped {set_path.name} (manual_edit: true)")
            sets_skipped += 1
            continue

        sections_yaml = "[" + ", ".join(f'"{s}"' for s in sections) + "]"
        fm = [
            "---",
            f'title: "{title}"',
            f"slug: {slug}",
            f"made_under_sections: {sections_yaml}",
            f"gazette_date: {gazette_date}",
            f"issuing_authority: UIDAI",
            f"status: in-force",
            f'source_pdf_url: "{pdf_url}"',
            f"item_count: {len(seen_nums)}",
        ]
        if original_pdf_url:
            fm.append(f'original_pdf_url: "{original_pdf_url}"')
        if original_as_of:
            fm.append(f"original_as_of: {original_as_of}")
        fm.append("---")
        fm.append("")
        set_path.write_text("\n".join(fm))
        sets_written += 1
        print(f"  wrote {set_path.name} (set: {len(seen_nums)} regulations)")

    print(
        f"\nSets: {sets_written} written, {sets_skipped} skipped"
        f"\nItems: {items_written} written, {items_skipped} skipped"
    )

    print("\nParsing as-enacted originals…")
    o_written, o_skipped = parse_originals()
    print(f"Original items: {o_written} written, {o_skipped} skipped")


if __name__ == "__main__":
    main()
