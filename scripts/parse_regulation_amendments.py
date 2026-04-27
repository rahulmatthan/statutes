"""Parse each amending UIDAI regulation PDF into a structured `changes:` list.

Each amending regulation is a Gazette notification that says, in plain English:

    In the principal regulations, in regulation 3, after sub-regulation (4),
    the following sub-regulation shall be inserted, namely:—
        "(5) The Authority may, for omitting or deactivating an Aadhaar
        number…"

This module reads the English section of each amending PDF, walks each
numbered paragraph, and extracts:
    - target (e.g., "regulation 3, sub-regulation (4)")
    - kind (substituted | inserted | omitted | renumbered)
    - before (verbatim, where present)
    - after (verbatim, where present)
    - note (free-form context)

Files with `manual_edit: true` are preserved.

Coverage: this parser handles the most common phrasings — substitution of
words, substitution of clauses/regulations, insertion of new clauses or
regulations, and omission of words. Unusual phrasings fall through with a
"raw" note containing the original instruction text — flag with manual_edit
and edit by hand if the auto-extraction is wrong.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib_parse import is_manual_edit


# ---------------------------------------------------------------------------
# Catalogue: same list of amending instruments as before, with metadata.
# ---------------------------------------------------------------------------

AMENDMENTS = [
    ("enrolment-and-update-2016", "2023-10-10",
     "The Aadhaar (Enrolment and Update) Amendment Regulations, 2023",
     "https://uidai.gov.in/images/Notification_Enrolement_and_Update.pdf"),
    ("enrolment-and-update-2016", "2024-01-16",
     "The Aadhaar (Enrolment and Update) Amendment Regulations, 2024",
     "https://uidai.gov.in/images/The_Aadhaar_Enrolment_and_Update_Amendment_Regulations_2024_published_on_16_1_2024.pdf"),
    ("enrolment-and-update-2016", "2024-01-27",
     "The Aadhaar (Enrolment and Update) Second Amendment Regulations, 2024",
     "https://uidai.gov.in/images/The_Aadhaar_Enrolment_and_Update_Second_Amendment_Regulations_2024_published_on_27_1_2024.pdf"),
    ("enrolment-and-update-2016", "2025-07-30",
     "Aadhaar (Enrolment and Update) First Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_notification_dated_3072025.pdf"),
    ("enrolment-and-update-2016", "2025-08-22",
     "Aadhaar (Enrolment and Update) Second Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_Notification_dated_22_08_2025.pdf"),
    ("enrolment-and-update-2016", "2025-11-25",
     "Aadhaar (Enrolment and Update) Third Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_dated_25_nov_2025.pdf"),
    ("authentication-and-offline-verification-2021", "2023-10-10",
     "The Aadhaar (Authentication and Offline Verification) Amendment Regulations, 2023",
     "https://uidai.gov.in/images/Notification_Authentication_and_Offline_Verification.pdf"),
    ("authentication-and-offline-verification-2021", "2024-01-31",
     "The Aadhaar (Authentication and Offline Verification) Amendment Regulations, 2024",
     "https://uidai.gov.in/images/The_Aadhaar_Authentication_and_Offline_Verification_Amendment_Regulations_2024_published_on_31_1_2024.pdf"),
    ("authentication-and-offline-verification-2021", "2025-12-09",
     "Aadhaar (Authentication and Offline Verification) Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_dated_9_dec_2025.pdf"),
    ("sharing-of-information-2016", "2024-01-27",
     "The Aadhaar (Sharing of Information) Amendment Regulations, 2024",
     "https://uidai.gov.in/images/The_Aadhaar_Sharing_of_Information_Amendment_Regulations_2024_published_on_27_1_2024.pdf"),
    ("sharing-of-information-2016", "2025-08-21",
     "Aadhaar (Sharing of Information) First Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_Notification_dated_21_08_2025.pdf"),
    ("payment-of-fees-2023", "2024-01-31",
     "The Aadhaar (Payment of Fees for Performance of Authentication) Amendment Regulations, 2024",
     "https://uidai.gov.in/images/The_Aadhaar_Payment_of_Fees_for_Performance_of_Authentication_Amendment_Regulations_2024_published_on_31_1_2024.pdf"),
    ("payment-of-fees-2023", "2024-02-09",
     "Corrigendum — Aadhaar (Payment of Fees) Amendment Regulations, 2024",
     "https://uidai.gov.in/images/Corrigendum_Published_on_09_02_2024.pdf"),
    ("payment-of-fees-2023", "2025-10-29",
     "Aadhaar (Payment of Fees for Performance of Authentication) Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_Notification_Auth_II.pdf"),
    ("appointment-of-officers-2020", "2024-01-25",
     "Unique Identification Authority of India (Appointment of Officers and Employees) Amendment Regulations, 2024",
     "https://uidai.gov.in/images/The_Unique_Identification_Authority_of_India_Appointment_of_Officers_and_Employees_Amendment_Regulations_2024_published_on_25_1_2024.pdf"),
    ("appointment-of-officers-2020", "2025-10-17",
     "UIDAI (Appointment of Officers and Employees) Third Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_Notification_dated_17_10_2025.pdf"),
    ("salary-allowances-2020", "2025-10-31",
     "UIDAI (Salary, Allowances and other Terms and Conditions of Service of Employees) Amendment Regulations, 2025",
     "https://uidai.gov.in/images/Gazette_Notification_dated_31102025.pdf"),
]


# ---------------------------------------------------------------------------
# Locate the English portion of the bilingual amendment PDF
# ---------------------------------------------------------------------------

ENGLISH_HEADER_RE = re.compile(
    r"(?:UNIQUE\s+IDENTIFICATION\s+AUTHORITY\s+OF\s+INDIA|"
    r"^\s*F\.\s*No\.\s+|^\s*[GS]\.S\.R\.\s+\d+\(E\)|"
    r"In\s+exercise\s+of\s+the\s+powers\s+conferred\s+by)",
    re.MULTILINE,
)


_TRAILER_RE = re.compile(
    r"\b(?:[A-Z][A-Z\s]{2,}\s*,\s*(?:Director|Joint\s+Secretary|Secretary|"
    r"Add(?:l|itional)?\s*(?:\.|\s)\s*Secy?\.|Add(?:l|itional)?\s+Secretary)|"
    r"\[ADVT\.-|"
    r"Note\s*:\s*The\s+principal\s+regulations|"
    r"Uploaded\s+by\s+Dte\.\s+of\s+Printing|"
    r"Digitally\s+signed\s+by)",
)


def _strip_devanagari_lines(text: str) -> str:
    """Drop lines that are predominantly Devanagari (Hindi page headers leak
    into the English section between paragraphs).
    """
    out = []
    for line in text.split("\n"):
        non_space = [c for c in line if not c.isspace()]
        if not non_space:
            out.append(line)
            continue
        deva = sum(1 for c in non_space if "ऀ" <= c <= "ॿ")
        if deva > len(non_space) * 0.3:
            continue
        out.append(line)
    return "\n".join(out)


def extract_english(text: str) -> str:
    """Slice the bilingual amendment text to keep only the English portion,
    drop Devanagari page-header lines that leak through, and remove the
    signatory / publisher trailer that follows the substantive changes.
    """
    candidates = []
    for m in re.finditer(
        r"^\s*F\.\s*No\.\s+[A-Z0-9/.\-]+.*?\bIn\s+exercise\s+of\s+the\s+powers",
        text,
        re.MULTILINE | re.DOTALL,
    ):
        candidates.append(m.start())
    if not candidates:
        for m in re.finditer(
            r"\bIn\s+exercise\s+of\s+the\s+powers\s+conferred\s+by\b",
            text,
        ):
            candidates.append(m.start())
    eng = text[candidates[-1]:] if candidates else text

    eng = _strip_devanagari_lines(eng)

    tm = _TRAILER_RE.search(eng)
    if tm:
        eng = eng[:tm.start()].rstrip()
    return eng


# ---------------------------------------------------------------------------
# Top-level paragraph extraction
# ---------------------------------------------------------------------------

PARA_HEADING_RE = re.compile(r"^(\d+)\.\s+(.*)$", re.MULTILINE)


def split_paragraphs(text: str) -> list[tuple[int, str]]:
    """Split English text into numbered top-level paragraphs.

    Returns [(num, body), …] for each `<n>. …` paragraph. The body of a
    paragraph stretches from the heading to the next heading (or document end).
    """
    paragraphs: list[tuple[int, str]] = []
    matches = list(PARA_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        num = int(m.group(1))
        # Reject sequence breaks: a real paragraph N is preceded by N-1.
        if num > 1 and not any(p[0] == num - 1 for p in paragraphs):
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        paragraphs.append((num, body))
    return paragraphs


# ---------------------------------------------------------------------------
# Per-paragraph change extraction
# ---------------------------------------------------------------------------

# Quoted before/after text. Allow curly and straight quotes.
_Q = r"[\"'‘“]"
_QC = r"[\"'’”]"
_Q_OPEN = r"[\"'‘“’”]"

# A "qualifier" is a comma-separated list like "words, brackets and figures".
_QUALIFIER = (
    r"(?:words?|expressions?|figures?|brackets?|short\s+title|letters?)"
    r"(?:\s*,\s*(?:words?|expressions?|figures?|brackets?|letters?))*"
    r"(?:\s+and\s+(?:words?|expressions?|figures?|brackets?|letters?))?"
)

# Substitution patterns
SUBST_INLINE = re.compile(
    rf"for\s+the\s+{_QUALIFIER}\s+"
    rf"{_Q_OPEN}([^\"'’”]+){_Q_OPEN}"
    rf"(?:\s+wherever\s+they\s+occur)?"
    rf"\s*,\s*"
    rf"the\s+{_QUALIFIER}\s+"
    rf"{_Q_OPEN}([^\"'’”]+){_Q_OPEN}\s*"
    rf"shall\s+be\s+substituted",
    re.IGNORECASE | re.DOTALL,
)

SUBST_BLOCK = re.compile(
    rf"for\s+(clause\s+\([a-z0-9]+\)|sub[- ]?clause\s+\([ivxlcdm]+\)|"
    rf"sub[- ]?regulation\s+\(\d+[A-Za-z]?\)|"
    rf"regulation\s+\d+[A-Za-z]?|"
    rf"the\s+short\s+title|the\s+Explanation|paragraph\s+\([a-z0-9]+\))"
    rf"\s*,\s*the\s+following\s+(?:clause|sub[- ]?clause|sub[- ]?regulation|"
    rf"regulation|short\s+title|Explanation|paragraph)?\s*"
    rf"shall\s+be\s+substituted\s*,\s*namely\s*[:—\-–]+\s*"
    rf"{_Q_OPEN}([\s\S]+?){_Q_OPEN}\s*\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

INS_AFTER = re.compile(
    rf"after\s+(clause\s+\([a-z0-9]+\)|sub[- ]?clause\s+\([ivxlcdm]+\)|"
    rf"sub[- ]?regulation\s+\(\d+[A-Za-z]?\)|"
    rf"regulation\s+\d+[A-Za-z]?|"
    rf"the\s+word\s+{_Q_OPEN}[^\"'’”]+{_Q_OPEN}|"
    rf"the\s+words\s+{_Q_OPEN}[^\"'’”]+{_Q_OPEN})"
    rf"\s*,\s*the\s+following\s+(?:clause|sub[- ]?clause|sub[- ]?regulation|"
    rf"regulation|word|words)\s+shall\s+be\s+inserted\s*,?\s*namely\s*[:—\-–]+\s*"
    rf"{_Q_OPEN}([\s\S]+?){_Q_OPEN}\s*\.?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

INS_AFTER_WORDS = re.compile(
    rf"after\s+the\s+words?\s+{_Q_OPEN}([^\"'’”]+){_Q_OPEN}\s*,\s*"
    rf"the\s+(?:words?|brackets?(?:\s+and\s+(?:words?|figures?))?|"
    rf"expressions?|figures?)\s+"
    rf"{_Q_OPEN}([^\"'’”]+){_Q_OPEN}\s+shall\s+be\s+inserted",
    re.IGNORECASE | re.DOTALL,
)

OMIT_WORDS = re.compile(
    rf"the\s+(?:words?|expressions?|figures?|brackets?(?:\s+and\s+(?:words?|figures?))?)\s+"
    rf"{_Q_OPEN}([^\"'’”]+){_Q_OPEN}\s+shall\s+be\s+omitted",
    re.IGNORECASE,
)

OMIT_BLOCK = re.compile(
    r"(clause\s+\([a-z0-9]+\)|sub[- ]?regulation\s+\(\d+[A-Za-z]?\)|"
    r"regulation\s+\d+[A-Za-z]?)"
    r"\s+shall\s+be\s+omitted",
    re.IGNORECASE,
)

# Scope-prefix consumption. We only treat "in <thing>, " as scope when it
# appears at the start of the paragraph (or immediately after the canonical
# "In the principal regulations," opener). Once we hit an action verb
# (substituted / inserted / omitted) we stop accumulating scope — references
# inside the body of a substituted regulation must NOT pollute scope.
SCOPE_PREFIX_RE = re.compile(
    r"^\s*in\s+(regulation\s+\d+[A-Za-z]?|sub[- ]?regulation\s+\(\d+[A-Za-z]?\)|"
    r"clause\s+\([a-z0-9]+\)|sub[- ]?clause\s+\([ivxlcdm]+\)|"
    r"the\s+Explanation|paragraph\s+\([a-z0-9]+\)|"
    r"Chapter\s+[IVXLCDM]+[A-Z]*)\s*,\s*",
    re.IGNORECASE,
)

PRINCIPAL_REGS_RE = re.compile(
    r"^\s*In\s+the\s+(?:principal|said)\s+regulations\b\s*"
    r"(?:\([^)]*\))?\s*,?\s*"
    r"(?:\(\s*hereinafter\s+referred\s+to\s+as\s+the\s+principal\s+regulations\s*\)\s*,?\s*)?",
    re.IGNORECASE,
)

PRINCIPAL_REGS_NAMED_RE = re.compile(
    r"^\s*In\s+the\s+[A-Z][^,]+Regulations,\s+\d{4}\s*"
    r"\(\s*hereinafter\s+referred\s+to\s+as\s+the\s+principal\s+regulations\s*\)\s*,?\s*",
    re.IGNORECASE | re.DOTALL,
)


def _normalise(s: str) -> str:
    s = s.strip().rstrip(",.;:")
    return re.sub(r"\s+", " ", s)


def _build_target(scope: list[str], local: str | None) -> str:
    parts = [s for s in scope if s]
    if local:
        parts.append(local)
    return ", ".join(parts) if parts else ""


def _consume_scope_prefix(text: str) -> tuple[list[str], str]:
    """Strip "In the principal regulations, in regulation X, in sub-regulation Y,"
    from the front of the paragraph. Returns (scope_list, remaining_text).
    """
    rest = text
    # Optional "In the [principal/said] regulations, …"
    m = PRINCIPAL_REGS_NAMED_RE.match(rest) or PRINCIPAL_REGS_RE.match(rest)
    if m:
        rest = rest[m.end():]
    scope: list[str] = []
    while True:
        m = SCOPE_PREFIX_RE.match(rest)
        if not m:
            break
        scope.append(_normalise(m.group(1)))
        rest = rest[m.end():]
    return scope, rest


def _split_subactions(rest: str) -> list[str]:
    """Split the rest of a paragraph into sub-action chunks at "(a)…; and (b)…"
    style boundaries. Returns the raw text of each sub-action.
    """
    # Sub-actions are introduced by "(a) ", "(b) ", … at top level (not
    # nested inside the substituted text, which is wrapped in quotes).
    # Heuristic: split on `; \(([a-z])\)` or `; and \(([a-z])\)` boundaries
    # that occur OUTSIDE of any quote.
    parts: list[str] = []
    cur = []
    i = 0
    n = len(rest)
    quote_depth = 0
    open_q = "\"'‘“"
    close_q = "\"'’”"
    while i < n:
        ch = rest[i]
        if ch in open_q:
            quote_depth += 1
        elif ch in close_q and quote_depth > 0:
            quote_depth -= 1
        # Look for ";" or "; and" outside quotes followed by " (letter) "
        if quote_depth == 0 and ch == ";":
            ahead = rest[i + 1: i + 12]
            m = re.match(r"\s*(?:and\s+)?\(([a-z])\)\s+", ahead)
            if m:
                parts.append("".join(cur).strip())
                cur = []
                i += 1 + m.end()
                continue
        cur.append(ch)
        i += 1
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def _strip_subletter_prefix(text: str) -> str:
    """Drop a leading "(a) " sub-action label."""
    return re.sub(r"^\s*\(([a-z])\)\s+", "", text)


def parse_changes(paragraph: str) -> list[dict]:
    """Extract every change embedded in one numbered paragraph."""
    text = re.sub(r"\s+", " ", paragraph).strip()
    text = re.sub(r"^\d+\.\s*", "", text)

    # Strip the scope prefix once. Anything inside the substituted text body
    # (which contains its own "in regulation X" cross-references) is left
    # untouched, so it can't pollute scope.
    scope, rest = _consume_scope_prefix(text)

    # Split the remainder into sub-actions when it has "(a) …; and (b) …".
    chunks = _split_subactions(rest) if re.search(r";\s*(?:and\s+)?\([a-z]\)\s+", rest) else [rest]

    out: list[dict] = []

    for chunk in chunks:
        chunk = _strip_subletter_prefix(chunk)
        # Per-chunk: we may peel additional scope (e.g., "in sub-regulation
        # (3), …" inside a sub-action of a paragraph that already established
        # scope for "regulation 10").
        sub_scope, chunk_rest = _consume_scope_prefix(chunk)
        full_scope = scope + sub_scope

        out.extend(_parse_one_chunk(chunk_rest, full_scope))

    # Dedupe identical changes (a regex sometimes catches the same text twice).
    seen = set()
    deduped: list[dict] = []
    for c in out:
        key = (c["kind"], c.get("target", ""), c.get("before", ""), c.get("after", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped


def _parse_one_chunk(text: str, scope: list[str]) -> list[dict]:
    out: list[dict] = []

    for m in SUBST_INLINE.finditer(text):
        out.append({
            "kind": "substituted",
            "target": _build_target(scope, None),
            "before": _normalise(m.group(1)),
            "after": _normalise(m.group(2)),
            "note": None,
        })

    for m in SUBST_BLOCK.finditer(text):
        out.append({
            "kind": "substituted",
            "target": _build_target(scope, _normalise(m.group(1))),
            "before": None,
            "after": _normalise(m.group(2)),
            "note": None,
        })

    for m in INS_AFTER.finditer(text):
        out.append({
            "kind": "inserted",
            "target": _build_target(scope, f"after {_normalise(m.group(1))}"),
            "before": None,
            "after": _normalise(m.group(2)),
            "note": None,
        })

    for m in INS_AFTER_WORDS.finditer(text):
        out.append({
            "kind": "inserted",
            "target": _build_target(scope, f"after \"{_normalise(m.group(1))}\""),
            "before": None,
            "after": _normalise(m.group(2)),
            "note": None,
        })

    for m in OMIT_WORDS.finditer(text):
        out.append({
            "kind": "omitted",
            "target": _build_target(scope, None),
            "before": _normalise(m.group(1)),
            "after": None,
            "note": None,
        })

    for m in OMIT_BLOCK.finditer(text):
        target = _build_target(scope, _normalise(m.group(1)))
        if any(c.get("target") == target and c["kind"] == "omitted" for c in out):
            continue
        out.append({
            "kind": "omitted",
            "target": target,
            "before": None,
            "after": None,
            "note": None,
        })

    return out


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def yaml_block_string(s: str | None) -> str:
    if s is None:
        return ""
    s = s.strip()
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def render_changes_yaml(changes: list[dict]) -> str:
    if not changes:
        return "changes: []"
    lines = ["changes:"]
    for c in changes:
        lines.append(f"  - kind: {c['kind']}")
        target = c.get("target", "")
        if target:
            lines.append(f"    target: {yaml_block_string(target)}")
        if c.get("before"):
            lines.append(f"    before: {yaml_block_string(c['before'])}")
        if c.get("after"):
            lines.append(f"    after: {yaml_block_string(c['after'])}")
        if c.get("note"):
            lines.append(f"    note: {yaml_block_string(c['note'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    extracted_dir = ROOT / "source-pdfs/extracted"
    out_root = ROOT / "src/content/regulation-amendments"
    out_root.mkdir(parents=True, exist_ok=True)

    written = skipped = 0
    total_changes = 0

    for parent, date, title, pdf_url in AMENDMENTS:
        folder = out_root / parent
        folder.mkdir(parents=True, exist_ok=True)
        out_path = folder / f"{date}.md"

        if is_manual_edit(out_path):
            print(f"  skipped {parent}/{date}.md (manual_edit: true)")
            skipped += 1
            continue

        # Locate the matching extracted-text file.
        # Filenames look like: amend-<parent>-<base>.txt where <base> is the
        # original PDF filename without extension.
        candidates = list(extracted_dir.glob(f"amend-{parent}-*.txt"))
        # Try to match by date or by recognisable substring.
        text_path = None
        date_compact = date.replace("-", "")
        for c in candidates:
            stem = c.stem.lower()
            if date_compact in stem or date in stem:
                text_path = c
                break
            # date variants like 27_1_2024 / 27.01.2024
            d_parts = date.split("-")
            slashes = [
                f"{int(d_parts[2])}_{int(d_parts[1])}_{d_parts[0]}",
                f"{int(d_parts[2])}_{d_parts[1]}_{d_parts[0]}",
                f"{d_parts[2]}_{int(d_parts[1])}_{d_parts[0]}",
                f"{int(d_parts[2])}.{int(d_parts[1])}.{d_parts[0]}",
                f"{d_parts[2]}.{d_parts[1]}.{d_parts[0]}",
                f"{int(d_parts[2])}{d_parts[1]}{d_parts[0]}",
                f"{int(d_parts[2])}_{d_parts[1].zfill(2)}_{d_parts[0]}",
                f"{int(d_parts[2])}_{int(d_parts[1])}_{d_parts[0]}",
            ]
            if any(s in stem for s in slashes):
                text_path = c
                break
        if text_path is None and candidates:
            # Fall back to the most recently modified candidate.
            text_path = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]
        if text_path is None:
            print(f"  WARNING: no extracted text for {parent}/{date}")
            continue

        text = text_path.read_text()
        english = extract_english(text)
        paragraphs = split_paragraphs(english)

        # Skip paragraph 1 (Short title and commencement) — collect changes
        # from paragraphs 2+.
        all_changes: list[dict] = []
        for num, body in paragraphs:
            if num == 1:
                continue
            all_changes.extend(parse_changes(body))

        total_changes += len(all_changes)

        body_md_lines = [
            "---",
            f'title: "{title}"',
            f"parent: {parent}",
            f"gazette_date: {date}",
            f'source_pdf_url: "{pdf_url}"',
            render_changes_yaml(all_changes),
            "---",
            "",
        ]
        if all_changes:
            summary = (
                f"This amending instrument records {len(all_changes)} discrete "
                "change(s) to the principal regulations. Each change is "
                "captured in the `changes:` array above, with the verbatim "
                "wording where the gazette text quoted it."
            )
        else:
            summary = (
                "Auto-extraction did not find structured change records in "
                f"this PDF. See the [source PDF]({pdf_url}) for the full "
                "verbatim text. Add `manual_edit: true` and edit by hand to "
                "preserve a curated version."
            )
        body_md_lines.append(summary)
        body_md_lines.append("")

        out_path.write_text("\n".join(body_md_lines))
        print(f"  wrote {parent}/{date}.md ({len(all_changes)} changes)")
        written += 1

    print(
        f"\nWrote {written}, skipped {skipped}, "
        f"total {total_changes} change records extracted"
    )


if __name__ == "__main__":
    main()
