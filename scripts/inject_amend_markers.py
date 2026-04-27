"""Backfill `<span class="amend">` markers into regulation-item body files.

The principal-regulations consolidated PDFs from UIDAI don't carry
footnote-style amendment markers for every clause that was changed, so
`parse_regulations.py` produces flat `<p class="block …">` paragraphs with
no inline `<span class="amend">` wrappers. As a result, the per-clause
sidebar UI on a regulation page has nothing to click on.

This script walks every `regulation-amendments/<parent>/<date>.md`,
pulls out the structured `changes:` array (populated this session), and
for each change tries to find the corresponding paragraph in the matching
`regulation-items/<parent>/<num>.md` body and wrap it with a span carrying
the amendment metadata that `section-interactions.ts` already expects:

    <span class="amend amend-block"
          data-id="…" data-kind="…" data-date="…" data-by="…"
          data-target="…" data-before="…" data-note="…">…</span>

It only wraps paragraphs that don't already contain an `.amend` span, so
it's safe to re-run. It only handles the reliable cases (clause-level and
sub-regulation-level insertions and substitutions where the new wording
starts with a `(label)`); whole-regulation, schedule, and word-level
omissions are skipped (those are best surfaced by the timeline + the
per-instrument page).

Usage:
    python3 scripts/inject_amend_markers.py
    python3 scripts/inject_amend_markers.py --dry-run
"""

from __future__ import annotations
import argparse
import html
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

ITEMS_ROOT = ROOT / "src/content/regulation-items"
AMENDS_ROOT = ROOT / "src/content/regulation-amendments"


# ---------------------------------------------------------------------------
# Target parsing
# ---------------------------------------------------------------------------

# Top-level regulation: "regulation 12", "regulation 25(1A)", "regulation 3A"
RE_REGULATION = re.compile(r"\bregulation\s+(\d+[A-Za-z]*)", re.IGNORECASE)

# Innermost paragraph label inside the target string. We pick the *last*
# label that appears, since scope chains from outer to inner:
#     "regulation 28, sub-regulation (1), clause (ea)"
#                                              ^^^^^ this one
RE_LABEL = re.compile(
    r"(?:sub-regulation|sub[- ]?clause|clause|paragraph)\s+\(([^)]+)\)",
    re.IGNORECASE,
)


def label_from_after(after: str | None) -> str | None:
    """If the `after` text starts with `(X) `, return `(X)`."""
    if not after:
        return None
    m = re.match(r"\s*(\([A-Za-z0-9]+\))\s+", after)
    return m.group(1) if m else None


def derive_anchor(change: dict) -> tuple[str, str | None] | None:
    """Return (item_num, label) where this change should be marked, or None.

    item_num is the regulation number ("12", "3a") within the parent set;
    label is the paragraph prefix to find in the body ("(1)", "(ac)") OR
    None to mean "wrap the whole body of this regulation file".
    """
    target = change.get("target") or ""
    after = change.get("after")
    kind = change.get("kind", "")

    # "after regulation N" insertion: find the new regulation's number from
    # the leading token of the `after` text (e.g. "5. Doing of act…", or
    # "32. Doing of act…", or "(5) …"). The new regulation gets its own
    # body file named after the new number, and we wrap the whole body.
    after_reg_match = re.match(
        r"^\s*(?:after\s+)?regulation\s+(\d+[A-Za-z]*)\s*$", target, re.I,
    )
    if after_reg_match is None:
        after_reg_match = re.match(
            r"^\s*after\s+regulation\s+(\d+[A-Za-z]*)\s*$", target, re.I,
        )
    if kind == "inserted" and re.match(r"^\s*after\s+regulation\b", target, re.I):
        # New regulation number from leading "N." of after text.
        if after:
            mn = re.match(r"^\s*[\(]?(\d+[A-Za-z]?)[\)]?\.\s", after)
            if mn:
                return mn.group(1).lower(), None
        return None

    m = RE_REGULATION.search(target)
    if not m:
        return None
    item_num = m.group(1).lower()

    # Special case: target "regulation N(K)" — paren-attached subscope.
    paren = re.match(r"^\s*regulation\s+\d+[A-Za-z]*\(([^)]+)\)", target, re.I)
    if paren:
        return item_num, f"({paren.group(1)})"

    # Prefer the label baked into the `after` text — it's the wording the
    # consolidated PDF actually shows.
    after_label = label_from_after(after)
    if after_label:
        return item_num, after_label

    # Otherwise the innermost label inside the target string.
    labels = RE_LABEL.findall(target)
    if labels:
        return item_num, f"({labels[-1]})"

    # No sub-label means whole-regulation. Substitution → wrap whole body.
    if kind in {"substituted", "inserted"} and re.fullmatch(
        r"\s*regulation\s+\d+[A-Za-z]*\s*", target, re.I,
    ):
        return item_num, None

    return None


# ---------------------------------------------------------------------------
# Body wrapping
# ---------------------------------------------------------------------------

# Match a single paragraph that starts with `<label>`. We intentionally
# require the full `<p class="block …">` opener so we don't false-positive
# on prose that happens to start with `(1)`.
def make_paragraph_re(label: str) -> re.Pattern:
    label_esc = re.escape(label)
    return re.compile(
        r'(?P<open><p class="block (?:subsection|clause|subclause|proviso|explanation)">)'
        r"\s*(?P<label>" + label_esc + r")\s+"
        r"(?P<body>[^<]*(?:<[^p][^>]*>[^<]*)*?)"
        r"(?P<close></p>)",
        re.DOTALL,
    )


def already_wrapped(paragraph_html: str) -> bool:
    return 'class="amend' in paragraph_html


def open_amend_span(change: dict, parent: str, date: str) -> str:
    by = f"{parent}/{date}"
    parts = ['<span class="amend amend-block"']
    parts.append(f' data-id="{html.escape(by)}"')
    parts.append(f' data-kind="{html.escape(change["kind"])}"')
    parts.append(f' data-date="{html.escape(date)}"')
    parts.append(f' data-by="{html.escape(by)}"')
    if change.get("target"):
        parts.append(f' data-target="{html.escape(change["target"])}"')
    if change.get("before"):
        parts.append(f' data-before="{html.escape(change["before"])}"')
    if change.get("note"):
        parts.append(f' data-note="{html.escape(change["note"])}"')
    parts.append(">")
    return "".join(parts)


def wrap_paragraph(body: str, label: str, change: dict, parent: str, date: str) -> tuple[str, bool]:
    """Wrap the body of the paragraph starting with `label` in an .amend span.

    Returns (new_body, did_change). did_change is False if no matching
    paragraph was found, or if it was already wrapped.
    """
    pattern = make_paragraph_re(label)
    m = pattern.search(body)
    if not m:
        return body, False

    full = m.group(0)
    if already_wrapped(full):
        return body, False

    open_span = open_amend_span(change, parent, date)
    inner = m.group("label") + " " + m.group("body")
    new_paragraph = f'{m.group("open")}{open_span}{inner}</span>{m.group("close")}'

    return body[: m.start()] + new_paragraph + body[m.end():], True


WHOLE_BODY_RE = re.compile(
    r'(<div class="statute-body">)(.*?)(</div>)', re.DOTALL,
)


def wrap_whole_body(body: str, change: dict, parent: str, date: str) -> tuple[str, bool]:
    """Wrap the entire <div class="statute-body"> contents in an .amend span.

    Used for whole-regulation insertions/substitutions. Skips if any child
    paragraph already carries an `.amend` span — re-running stays idempotent.
    """
    m = WHOLE_BODY_RE.search(body)
    if not m:
        return body, False
    inner = m.group(2)
    if 'class="amend' in inner:
        return body, False
    open_span = open_amend_span(change, parent, date)
    new_inner = f"{open_span}{inner}</span>"
    return body[: m.start(2)] + new_inner + body[m.end(2):], True


# ---------------------------------------------------------------------------
# Frontmatter handling
# ---------------------------------------------------------------------------

FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    m = FM_RE.match(text)
    if not m:
        raise ValueError("missing frontmatter")
    return m.group(1), m.group(2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be wrapped, don't write files.")
    args = ap.parse_args()

    # Load the changes from every amendment file.
    amend_files = sorted(AMENDS_ROOT.glob("*/*.md"))
    if not amend_files:
        print("No amendment files found.")
        return

    # Group changes by (parent, item_num) so each item is rewritten once.
    pending: dict[tuple[str, str], list[tuple[str, str, dict]]] = {}
    skipped_targets: list[tuple[str, str, str]] = []

    for af in amend_files:
        text = af.read_text()
        try:
            fm, _body = split_frontmatter(text)
        except ValueError:
            continue
        data = yaml.safe_load(fm)
        parent = data["parent"]
        date = data["gazette_date"].isoformat() if hasattr(data["gazette_date"], "isoformat") else str(data["gazette_date"])
        changes = data.get("changes") or []
        for change in changes:
            anchor = derive_anchor(change)
            if not anchor:
                skipped_targets.append((parent, date, change.get("target") or "(no target)"))
                continue
            item_num, label = anchor
            pending.setdefault((parent, item_num), []).append((date, label, change))

    # Now walk each item body once, wrapping every applicable change.
    written = 0
    wrapped = 0
    misses = 0

    for (parent, item_num), entries in sorted(pending.items()):
        path = ITEMS_ROOT / parent / f"{item_num}.md"
        if not path.exists():
            print(f"  miss   {parent}/{item_num}: no body file")
            misses += len(entries)
            continue
        text = path.read_text()
        try:
            fm, body = split_frontmatter(text)
        except ValueError:
            print(f"  miss   {parent}/{item_num}: no frontmatter")
            misses += len(entries)
            continue

        new_body = body
        local_wrapped = 0
        for date, label, change in entries:
            if label is None:
                new_body, did = wrap_whole_body(new_body, change, parent, date)
            else:
                new_body, did = wrap_paragraph(new_body, label, change, parent, date)
            if did:
                local_wrapped += 1
            else:
                misses += 1

        if local_wrapped == 0:
            continue

        wrapped += local_wrapped
        if args.dry_run:
            print(f"  dry    {parent}/{item_num}.md (+{local_wrapped})")
        else:
            path.write_text(f"---\n{fm}\n---\n{new_body}")
            written += 1
            print(f"  wrote  {parent}/{item_num}.md (+{local_wrapped})")

    print(
        f"\n{written} item file(s) updated, {wrapped} marker(s) wrapped, "
        f"{misses} change(s) without a paragraph match, "
        f"{len(skipped_targets)} target(s) couldn't be parsed."
    )
    if skipped_targets and args.dry_run:
        print("\nUnparsed targets (these stay only on the per-instrument page):")
        for p, d, t in skipped_targets[:30]:
            print(f"  {p}/{d}: {t}")


if __name__ == "__main__":
    main()
