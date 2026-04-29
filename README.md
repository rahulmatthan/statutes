# Aadhaar Statutes

**Live:** [exmachina.in/statutes/aadhaar](https://exmachina.in/statutes/aadhaar/)

Part of the [exmachina.in/statutes](https://exmachina.in/statutes/) portal.

A navigable, cross-referenced edition of the **Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act, 2016** and all rules and regulations made under it.

For each section of the Act, the site shows:

1. **Current text** (as on the most recent consolidation).
2. **Amendment history** with verbatim *before* and *after* wording for each change.
3. **Made under this section** — every Rule and Regulation that names this section in its enabling clause.

Modelled on [legislation.gov.uk](https://www.legislation.gov.uk/) (Timeline of Changes) and [Cornell LII](https://www.law.cornell.edu/uscode) (per-section source credits).

## Stack

- **Astro** static site with content collections and Zod-validated frontmatter (`src/content.config.ts`).
- **Tailwind CSS v4** for styling.
- **React island** for the side-by-side amendment diff (`src/components/AmendmentDiff.tsx`).
- **Pagefind** for client-side full-text search.

Output is fully static; deploys to Cloudflare Pages, Vercel, Netlify, or any S3-style host.

## Layout

```
src/content/
  sections/                    one file per Act section (s-1.md ... s-59.md, plus inserted/omitted)
  amendments/                  amending Acts and Ordinances (2019-amendment-act, 2019-ordinance)
  rules/                       Central Government rule SETS — slim metadata (5 sets)
  rule-items/<set>/            individual rules within a set, one file each
  regulations/                 UIDAI regulation SETS — slim metadata (8 sets)
  regulation-items/<set>/      individual regulations within a set, one file each (~220)
  regulation-amendments/       amending regulations, grouped by parent (17 amendments, 2023–2025)
src/pages/
  index.astro                  landing
  act/index.astro              Arrangement of Sections
  act/s/[section].astro        per-section page
  amendments/                  amending instruments
  rules/                       Central Government rules
  regulations/                 UIDAI regulations and their amendment chains
  search.astro                 Pagefind UI
source-pdfs/                   archive of every UIDAI PDF used to build the site
scripts/                       Python ingestion scripts (regenerable)
```

## URL contract

Citation-friendly. Once public, these URLs do not move without redirects.

- `/act/s/3` — Section 3 of the Aadhaar Act
- `/act/s/3#history-2019-07-25` — deep link to a specific amendment block
- `/amendments/2019-amendment-act`
- `/rules/adjudication-of-penalties-2021` — set landing (arrangement of rules)
- `/rules/adjudication-of-penalties-2021/r/3` — Rule 3 of that set
- `/regulations/enrolment-and-update-2016` — set landing (arrangement of regulations)
- `/regulations/enrolment-and-update-2016/r/3` — Regulation 3 of that set
- `/regulations/enrolment-and-update-2016/a/2024-01-16` — single amending regulation, standalone

## Development

```bash
npm install
npm run dev          # http://localhost:4321
npm run build        # static output to dist/, also builds Pagefind index
```

To regenerate content from the source PDFs in `source-pdfs/`:

```bash
npm run ingest       # runs all three Python parsers
```

The Python scripts under `scripts/` extract section text from `pdftotext -layout` output.

## Hand-editing content

PDF extraction is imperfect — OCR errors, gazette annotations, and odd line breaks creep in. Every content file under `src/content/` is plain markdown with frontmatter, so you fix mistakes by editing the file directly. Astro's dev server hot-reloads the change.

Quick path:

1. Run `npm run dev` and open the page that has the bad text.
2. Find the source file: `python3 scripts/find_file.py /regulations/payment-of-fees-2023/r/5` prints the path to edit.
3. Open the file, fix the body, add `manual_edit: true` to the frontmatter, save.
4. The page reloads with your changes; `npm run ingest` will skip the file from now on.

**Full reference, including the body's HTML structure and frontmatter for every collection, lives at [`docs/EDITING.md`](docs/EDITING.md).** Read that before starting a long cleanup pass.

## Source documents

All current PDFs come from [uidai.gov.in/en/about-uidai/legal-framework.html](https://uidai.gov.in/en/about-uidai/legal-framework.html). Each Rule, Regulation, or amendment file links out to its UIDAI URL via `source_pdf_url` in frontmatter — we don't rehost the PDFs.

**As-enacted (original) versions** of regulations come from the Wayback Machine — UIDAI overwrites its consolidated PDFs in place, so the only public source for the original 2016/2020/2021 text is archive.org. Each regulation set carries an `original_pdf_url` field linking to the earliest Wayback snapshot. The set landing page exposes it as an "As enacted" link alongside the current consolidated PDF, and per-regulation pages render an "as-enacted" version pill in the timeline that toggles the body to the original wording. Local copies are archived in `source-pdfs/regulation-base-original/`, extracted text in `source-pdfs/extracted/orig-*.txt`, and parsed per-item files in `src/content/regulation-items-original/`.

## Status

This is a working **starting point**, not a finished product. What's done:

- 69 Act sections extracted and routed, with chapter grouping and amendment-marker detection.
- 5 Central Government rules with **full extracted text**, structured the same way as Act sections (rule-by-rule headings, sub-rule paragraphs, clauses, sub-clauses, provisos).
- 8 base UIDAI regulations with **full extracted text** — every regulation rendered as its own block with sub-regulation/clause structure and inline amendment markers (clickable, with side-panel popover).
- 17 amending regulations (2023–2025) with frontmatter pointing to the gazette PDFs.
- Cross-references between sections and rules/regulations via `made_under_sections` frontmatter — automatic, data-driven.
- Amendment timeline component on every section.
- Side-by-side word-level diff (React island) wherever an amendment has both `before` and `after` text.
- Pagefind full-text search across the entire site.

What still needs hand-review (not blocking — site builds and runs today):

- **Body text cleanup.** PDF extraction sometimes captures embedded NOTIFICATION blocks; line wrapping and sub-section breaks need polishing on a per-section basis.
- **Amendment verbatim text.** The script captures *before* text where the consolidated PDF's footnote contains it (e.g., "before substitution, stood as under: ..."). For inserted-only amendments and substitutions where the footnote text is wrapped weirdly, the `before` field is left empty for hand-fill.
- **Regulation full text.** Each base regulation currently has a frontmatter-driven Arrangement-of-Regulations index plus a link to the source PDF. Per-regulation extraction (one markdown file per regulation within an instrument) is a follow-up pass.
- **Regulation amendment changes.** The 17 amending regulations have empty `changes` arrays — these need hand-review of each gazette notification to capture the verbatim regulation-level diffs.

Each gap above is a documented data-improvement task; none is blocking. The information architecture is complete and stable.
