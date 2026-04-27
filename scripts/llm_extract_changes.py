"""LLM-based fallback extractor for amending-regulation `changes:` arrays.

The regex parser in `parse_regulation_amendments.py` handles ~75 % of cases.
The remaining 25 % — schedule edits, "wherever they occur" qualifiers, list
qualifiers, novel phrasings — fail silently with `changes: []`. Hand-editing
200+ items doesn't scale, so this script asks Claude to read the gazette
English text and emit the same schema-shaped change records as the regex
parser.

Pipeline shape:
    extracted/amend-<parent>-<base>.txt
        → extract_english() (reused from regex parser, drops Hindi/trailer)
        → Claude with forced tool use (schema = regulationAmendments.changes)
        → src/content/regulation-amendments/<parent>/<date>.md  (changes: filled)

Behaviour rules:
    * Files with `manual_edit: true` are NEVER overwritten.
    * Existing frontmatter (title / parent / gazette_date / source_pdf_url) is
      preserved verbatim — only the `changes:` array is replaced.
    * Per-input results are cached at `.cache/llm/<sha256>.json`. Re-runs of
      the same source text are free.
    * The system prompt + tool schema are stable, so prompt caching makes
      repeated calls within one run hit the cache (verify via
      `usage.cache_read_input_tokens` — a zero across multiple calls means
      something silently invalidated the prefix).

Usage:
    export ANTHROPIC_API_KEY=...
    python3 scripts/llm_extract_changes.py                  # all empty/sparse
    python3 scripts/llm_extract_changes.py --target enrolment-and-update-2016/2024-01-16
    python3 scripts/llm_extract_changes.py --all            # every amendment
    python3 scripts/llm_extract_changes.py --dry-run        # print, don't write
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib_parse import is_manual_edit
from parse_regulation_amendments import (
    AMENDMENTS,
    extract_english,
    render_changes_yaml,
)


MODEL = "claude-opus-4-7"

EXTRACT_TOOL = {
    "name": "record_changes",
    "description": (
        "Record every discrete change made by this amending regulation to its "
        "principal regulations. Each change must match exactly one of the four "
        "kinds. Always preserve verbatim quoted text (with the surrounding "
        "quotation marks stripped) for `before`/`after`. Do not paraphrase. If "
        "no changes are present (e.g., the document is purely a corrigendum "
        "with no substantive change), return an empty `changes` array."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["substituted", "inserted", "omitted", "renumbered"],
                            "description": (
                                "The action verb used by the gazette. "
                                "'substituted' replaces existing text with new text; "
                                "'inserted' adds new text without removing anything; "
                                "'omitted' deletes text; "
                                "'renumbered' changes the number/letter of an existing "
                                "provision without changing its substance."
                            ),
                        },
                        "target": {
                            "type": "string",
                            "description": (
                                "Where the change applies, e.g. "
                                "'regulation 3, sub-regulation (4)' or "
                                "'after regulation 4' or "
                                "'Schedule, paragraph (b)'. Use the exact "
                                "labels the gazette uses; chain scope from "
                                "outer to inner with commas. For inserts, "
                                "include the anchor (e.g., 'after regulation 4')."
                            ),
                        },
                        "before": {
                            "type": "string",
                            "description": (
                                "The verbatim text being replaced or omitted, "
                                "with surrounding quotation marks stripped. "
                                "Required for 'substituted' and 'omitted' "
                                "when the gazette quotes the prior wording. "
                                "Omit if the gazette does not quote it (some "
                                "block substitutions only quote the new text)."
                            ),
                        },
                        "after": {
                            "type": "string",
                            "description": (
                                "The verbatim new text, with quotation marks "
                                "stripped. Required for 'substituted' and "
                                "'inserted'. Preserve the gazette's internal "
                                "structure (sub-regulation labels, provisos, "
                                "explanations) as plain inline text, joined "
                                "with single spaces."
                            ),
                        },
                        "note": {
                            "type": "string",
                            "description": (
                                "Optional free-form context — useful when the "
                                "change is unusual (renumbering chain, "
                                "conditional commencement, dependency on "
                                "another paragraph). Leave empty for "
                                "straightforward changes."
                            ),
                        },
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["changes"],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """You are a legislative text extractor for Indian gazette \
notifications.

Each input is the English portion of an amending regulation published in the \
Gazette of India. The document amends a "principal regulations" by inserting, \
substituting, omitting, or renumbering provisions. Your job is to enumerate \
every discrete change as a structured record, calling the `record_changes` \
tool exactly once.

Rules:

1. Skip paragraph 1 ("Short title and commencement") — it is boilerplate, not \
   a change to the principal regulations.
2. Each top-level numbered paragraph (2, 3, 4, …) usually describes ONE \
   change. Some paragraphs bundle multiple changes via "(a) … and (b) …" \
   sub-actions — split those into separate change records, but keep the \
   shared scope (e.g. "in regulation 3") on every record.
3. Use exact gazette wording for `target` (e.g. "regulation 3, sub-regulation \
   (4)" or "after regulation 4"). Chain scope from outer to inner with \
   commas.
4. Preserve verbatim quoted text in `before` / `after`. Strip the quotation \
   marks. Collapse internal newlines to single spaces. Keep the gazette's \
   sub-numbering (e.g., the "(1) …" and "(2) …" inside an inserted regulation \
   block) as plain inline text.
5. If a substitution gives only the new wording (block-substitution style), \
   leave `before` empty and put the new wording in `after`.
6. If an omission gives only the prior wording, fill `before` and leave \
   `after` empty.
7. If the document is a corrigendum that only fixes a typo without changing \
   substance, you may either record the typo fix as a single substitution \
   change or — when there is genuinely nothing substantive — return an empty \
   array.
8. Return changes in the order the gazette presents them.
"""


def cache_path(text: str) -> Path:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ROOT / ".cache" / "llm" / f"{h}.json"


def call_claude(client: anthropic.Anthropic, english: str) -> tuple[list[dict], dict]:
    """Call Claude with forced tool use; return (changes, usage_dict)."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_changes"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract every change in the gazette text below.\n\n"
                            "<gazette>\n"
                            f"{english}\n"
                            "</gazette>"
                        ),
                    }
                ],
            }
        ],
    )

    tool_block = next(
        (b for b in response.content if b.type == "tool_use"), None,
    )
    if tool_block is None:
        raise RuntimeError(
            "Claude did not call the record_changes tool. "
            f"Stop reason: {response.stop_reason}"
        )

    changes = tool_block.input.get("changes", [])

    u = response.usage
    usage = {
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    return changes, usage


def estimate_cost(usage: dict) -> float:
    # Opus 4.7 pricing per 1M tokens: $5 input, $25 output, $0.50 cache read,
    # $6.25 cache write.
    base_in = (usage["input_tokens"] - usage["cache_read_input_tokens"]
               - usage["cache_creation_input_tokens"])
    cost = (
        base_in * 5.0 / 1_000_000
        + usage["cache_read_input_tokens"] * 0.50 / 1_000_000
        + usage["cache_creation_input_tokens"] * 6.25 / 1_000_000
        + usage["output_tokens"] * 25.0 / 1_000_000
    )
    return cost


# ---------------------------------------------------------------------------
# Markdown read/write
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n(.*)$", re.DOTALL)


def parse_existing_md(path: Path) -> tuple[dict, str]:
    """Return (frontmatter_lines_dict, body_text). The dict preserves the
    original frontmatter line-for-line as a `lines` key plus a parsed shallow
    mapping for inspection.
    """
    text = path.read_text()
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{path} has no YAML frontmatter")
    fm_text, body = m.group(1), m.group(2)
    return {"_raw": fm_text, "_path": str(path)}, body


def render_md(fm_raw: str, changes: list[dict], pdf_url: str | None) -> str:
    """Strip the existing `changes:` block from `fm_raw` and append a fresh
    one. Everything else in the frontmatter is left untouched.
    """
    # Drop existing changes block: from a `changes:` line up to (but not
    # including) the next non-indented key OR the end.
    lines = fm_raw.split("\n")
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^changes\s*:", line):
            i += 1
            while i < len(lines) and (
                lines[i].startswith(" ") or lines[i].strip() == ""
            ):
                i += 1
            continue
        out_lines.append(line)
        i += 1
    new_fm = "\n".join(l for l in out_lines if l != "" or True).rstrip() + "\n"
    new_fm += render_changes_yaml(changes) + "\n"

    if changes:
        summary = (
            f"This amending instrument records {len(changes)} discrete "
            "change(s) to the principal regulations. Each change is captured "
            "in the `changes:` array above, with the verbatim wording where "
            "the gazette text quoted it."
        )
    else:
        link = f"[source PDF]({pdf_url})" if pdf_url else "the source PDF"
        summary = (
            "Auto-extraction did not find structured change records in this "
            f"PDF. See {link} for the full verbatim text. Add "
            "`manual_edit: true` and edit by hand to preserve a curated "
            "version."
        )

    return f"---\n{new_fm}---\n\n{summary}\n"


# ---------------------------------------------------------------------------
# Targeting which amendments to run
# ---------------------------------------------------------------------------

def existing_change_count(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text()
    if re.search(r"^changes:\s*\[\s*\]\s*$", text, re.MULTILINE):
        return 0
    return len(re.findall(r"^\s+-\s+kind\s*:", text, re.MULTILINE))


def select_targets(args, out_root: Path) -> list[tuple[str, str, str, str]]:
    if args.target:
        wanted = set(args.target)
        return [a for a in AMENDMENTS if f"{a[0]}/{a[1]}" in wanted]
    if args.all:
        return list(AMENDMENTS)
    # default: empty + sparse (≤2 changes)
    out: list[tuple[str, str, str, str]] = []
    for a in AMENDMENTS:
        parent, date, *_ = a
        path = out_root / parent / f"{date}.md"
        if existing_change_count(path) <= 2:
            out.append(a)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--target", action="append", default=[],
                    help="Run only on <parent>/<date> (repeatable).")
    ap.add_argument("--all", action="store_true",
                    help="Run on every amendment, ignoring existing changes.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the changes Claude returns; don't write files.")
    ap.add_argument("--no-cache", action="store_true",
                    help="Bypass the disk cache; always call Claude.")
    args = ap.parse_args()

    extracted_dir = ROOT / "source-pdfs/extracted"
    out_root = ROOT / "src/content/regulation-amendments"
    out_root.mkdir(parents=True, exist_ok=True)

    targets = select_targets(args, out_root)
    if not targets:
        print("No amendments matched the target filter.")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        sys.exit(2)

    client = anthropic.Anthropic()

    written = skipped = cached = 0
    total_cost = 0.0
    total_changes = 0

    for parent, date, title, pdf_url in targets:
        out_path = out_root / parent / f"{date}.md"

        if is_manual_edit(out_path):
            print(f"  skip   {parent}/{date}.md (manual_edit)")
            skipped += 1
            continue

        # Resolve the extracted-text file. Reuse the same date-matching
        # heuristic as the regex parser so filename variants are handled.
        candidates = list(extracted_dir.glob(f"amend-{parent}-*.txt"))
        text_path = _match_text_file(candidates, date)
        if text_path is None:
            print(f"  WARN   no extracted text for {parent}/{date}")
            continue

        english = extract_english(text_path.read_text())

        cp = cache_path(english)
        if not args.no_cache and cp.exists():
            cached_data = json.loads(cp.read_text())
            changes = cached_data["changes"]
            cached += 1
            print(f"  cache  {parent}/{date}.md ({len(changes)} changes)")
        else:
            try:
                changes, usage = call_claude(client, english)
            except Exception as e:
                print(f"  ERROR  {parent}/{date}: {e}")
                continue
            cost = estimate_cost(usage)
            total_cost += cost
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(
                {"changes": changes, "usage": usage}, indent=2,
            ))
            print(
                f"  llm    {parent}/{date}.md "
                f"({len(changes)} changes; "
                f"in={usage['input_tokens']} "
                f"cache_read={usage['cache_read_input_tokens']} "
                f"out={usage['output_tokens']} "
                f"${cost:.4f})"
            )

        total_changes += len(changes)

        if args.dry_run:
            for c in changes:
                print(f"      - [{c['kind']}] target={c.get('target', '')!r}")
                if c.get("before"):
                    print(f"          before: {c['before'][:100]!r}")
                if c.get("after"):
                    print(f"          after:  {c['after'][:100]!r}")
            continue

        # Read existing markdown to preserve the rest of the frontmatter.
        if not out_path.exists():
            # Build a fresh file with the canonical frontmatter.
            fm_raw = (
                f'title: "{title}"\n'
                f"parent: {parent}\n"
                f"gazette_date: {date}\n"
                f'source_pdf_url: "{pdf_url}"\n'
            )
        else:
            fm_info, _body = parse_existing_md(out_path)
            fm_raw = fm_info["_raw"]

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_md(fm_raw, changes, pdf_url))
        written += 1

    print(
        f"\n{written} written, {cached} from cache, {skipped} skipped — "
        f"{total_changes} total changes; ${total_cost:.2f} this run"
    )


def _match_text_file(candidates: list[Path], date: str) -> Path | None:
    if not candidates:
        return None
    date_compact = date.replace("-", "")
    d_parts = date.split("-")
    variants = {
        date_compact, date,
        f"{int(d_parts[2])}_{int(d_parts[1])}_{d_parts[0]}",
        f"{int(d_parts[2])}_{d_parts[1]}_{d_parts[0]}",
        f"{d_parts[2]}_{int(d_parts[1])}_{d_parts[0]}",
        f"{int(d_parts[2])}.{int(d_parts[1])}.{d_parts[0]}",
        f"{d_parts[2]}.{d_parts[1]}.{d_parts[0]}",
        f"{int(d_parts[2])}{d_parts[1]}{d_parts[0]}",
        f"{int(d_parts[2])}_{d_parts[1].zfill(2)}_{d_parts[0]}",
    }
    for c in candidates:
        stem = c.stem.lower()
        if any(v in stem for v in variants):
            return c
    return sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]


if __name__ == "__main__":
    main()
