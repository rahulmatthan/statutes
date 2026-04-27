"""Parse Central Government rule PDFs into structured markdown.

Each rule (Adjudication of Penalties 2021, Good Governance Authentication 2020,
…) is parsed into per-rule structured HTML files. Each rule lives at
src/content/rule-items/<set-slug>/<num>.md; the set itself is a slim metadata
file at src/content/rules/<set-slug>.md. Files with `manual_edit: true` are
preserved.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib_parse import is_manual_edit
from parse_regulations import (
    parse_document, write_item_file, render_item_body,
)


# ---------------------------------------------------------------------------
# Rule-set config: slug, full title, short title, made-under sections, date,
# source PDF URL, extracted-text filename.
# ---------------------------------------------------------------------------

RULES = [
    (
        "adjudication-of-penalties-2021",
        "The Unique Identification Authority of India (Adjudication of Penalties) Rules, 2021",
        "Adjudication of Penalties Rules, 2021",
        ["33A", "33B", "33C", "53(2)(ga)", "53(2)(gb)", "53(2)(h)"],
        "2021-10-29",
        "https://uidai.gov.in/images/Unique_Identification_Authority_of_India_Adjudication_of_Penalties_Rules_2021.pdf",
        "rule-adjudication-of-penalties-2021.txt",
    ),
    (
        "good-governance-authentication-2020",
        "The Aadhaar Authentication for Good Governance (Social Welfare, Innovation, Knowledge) Rules, 2020",
        "Good Governance Authentication Rules, 2020",
        ["4(4)(b)(ii)", "53(2)"],
        "2020-08-05",
        "https://uidai.gov.in/images/Aadhaar_Authentication_for_Good_Governance_Rules_2020.pdf",
        "rule-good-governance-authentication-2020.txt",
    ),
    (
        "annual-statement-of-accounts-2018",
        "The Unique Identification Authority of India (Form of Annual Statement of Accounts) Rules, 2018",
        "Annual Statement of Accounts Rules, 2018",
        ["26(1)", "53(2)(e)"],
        "2018-09-13",
        "https://uidai.gov.in/images/UIDAI_Form_of_Annual_statement_of_Accounts_Rules_2018.pdf",
        "rule-annual-statement-of-accounts-2018.txt",
    ),
    (
        "returns-and-annual-report-2018",
        "The Unique Identification Authority of India (Returns and Annual Report) Rules, 2018",
        "Returns and Annual Report Rules, 2018",
        ["27(1)", "27(2)", "53(2)(f)"],
        "2018-04-27",
        "https://uidai.gov.in/images/UIDAI-Returns-and-Annual-Report-Rules-2018-13062018.pdf",
        "rule-returns-and-annual-report-2018.txt",
    ),
    (
        "chairperson-service-conditions-2016",
        "The Unique Identification Authority of India (Terms and Conditions of Service of Chairperson and Members) Rules, 2016",
        "Chairperson and Members Service Rules, 2016",
        ["14(4)", "53(2)(b)"],
        "2016-07-12",
        "https://uidai.gov.in/images/notification_chairman_rules_13072016.pdf",
        "rule-chairperson-service-conditions-2016.txt",
    ),
]


def main() -> None:
    out_set_dir = ROOT / "src/content/rules"
    out_items_root = ROOT / "src/content/rule-items"
    out_set_dir.mkdir(parents=True, exist_ok=True)
    out_items_root.mkdir(parents=True, exist_ok=True)
    extracted_dir = ROOT / "source-pdfs/extracted"

    sets_written = sets_skipped = 0
    items_written = items_skipped = 0

    for slug, title, short_title, sections, gazette_date, pdf_url, txt_filename in RULES:
        text = (extracted_dir / txt_filename).read_text()
        # Rules don't have separately-tracked amendment instruments yet.
        items = parse_document(text, slug, set())

        items_dir = out_items_root / slug
        items_dir.mkdir(parents=True, exist_ok=True)

        seen_nums = set()
        for item in items:
            if item["number"] in seen_nums:
                continue
            seen_nums.add(item["number"])
            written, name = write_item_file(items_dir, slug, item, gazette_date)
            if written:
                items_written += 1
            else:
                print(f"  skipped {slug}/{name} (manual_edit: true)")
                items_skipped += 1

        set_path = out_set_dir / f"{slug}.md"
        if is_manual_edit(set_path):
            print(f"  skipped {set_path.name} (manual_edit: true)")
            sets_skipped += 1
            continue

        sections_yaml = "[" + ", ".join(f'"{s}"' for s in sections) + "]"
        fm = [
            "---",
            f'title: "{title}"',
            f'short_title: "{short_title}"',
            f"made_under_sections: {sections_yaml}",
            f"gazette_date: {gazette_date}",
            f"issuing_authority: Central Government",
            f"status: in-force",
            f'source_pdf_url: "{pdf_url}"',
            f"item_count: {len(seen_nums)}",
            "---",
            "",
        ]
        set_path.write_text("\n".join(fm))
        sets_written += 1
        print(f"  wrote {set_path.name} (set: {len(seen_nums)} rules)")

    print(
        f"\nSets: {sets_written} written, {sets_skipped} skipped"
        f"\nItems: {items_written} written, {items_skipped} skipped"
    )


if __name__ == "__main__":
    main()
