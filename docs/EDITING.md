# Hand-editing content

PDF extraction is imperfect. OCR errors, bad line wraps, footnote text leaking into bodies, and gazette artefacts all need fixing by hand. This document is the practical workflow.

## The 30-second version

1. **Find the file.** `python3 scripts/find_file.py /regulations/payment-of-fees-2023/r/5` prints the path.
2. **Edit it** in any editor. The body is HTML inside a markdown file.
3. **Add `manual_edit: true`** to the frontmatter to lock the file against re-ingest:

   ```yaml
   ---
   parent: payment-of-fees-2023
   number: "5"
   title: "Doing of act or thing related to delegated power or function"
   manual_edit: true
   status: inserted
   …
   ---
   ```

4. **Save.** If `npm run dev` is running, the page hot-reloads.

## Body HTML reference

The body is wrapped in `<div class="statute-body">…</div>`. Inside it:

| Pattern | Renders as |
|---|---|
| `<p class="block lead">First sentence…</p>` | Lead paragraph (no opener) |
| `<p class="block subsection">(1) text…</p>` | Sub-section, top level |
| `<p class="block clause">(a) text…</p>` | Clause, indented |
| `<p class="block subclause">(i) text…</p>` | Sub-clause, double-indented |
| `<p class="block proviso">Provided that …</p>` | Italic proviso |
| `<p class="block explanation">Explanation.— …</p>` | Indented gutter |

Inline amendment (highlighted phrase, click → side panel):

```html
<span class="amend"
      data-id="p3.1"
      data-kind="inserted"
      data-date="2019-07-25"
      data-by="2019-amendment-act"
      data-target="sub-section (3)"
      data-before="the previous wording"
      data-note="Inserted by Act 14 of 2019">
  the new wording
</span>
```

Block amendment (whole sub-section, has its own gutter strip):

```html
<p class="block subsection">
  <span class="amend amend-block" data-id="…" data-kind="inserted" …>
    (4) The Aadhaar number issued to an individual under sub-section (3) shall be …
  </span>
</p>
```

`data-kind` accepts `inserted`, `substituted`, `omitted`, `renumbered`, `amended`. `data-by` should be one of:

| `data-by` value | Links to |
|---|---|
| `2019-amendment-act` | `/amendments/2019-amendment-act` |
| `2019-ordinance` | `/amendments/2019-ordinance` |
| `<set-slug>/<YYYY-MM-DD>` | `/regulations/<set>/a/<YYYY-MM-DD>` (regulation amendments) |
| `original` | (no link) |

## Frontmatter reference

### Section files (`src/content/sections/s-<n>.md`)

```yaml
---
section: "3"                       # required, e.g., "3" or "3A"
title: "Aadhaar number"
chapter: "II — Enrolment"
chapter_order: 2
status: amended                    # original | amended | inserted | omitted
current_as_of: 2023-10-10
manual_edit: true                  # optional, set to preserve hand-edits
history:
  - date: 2016-03-25
    by: original
    kind: enacted
  - date: 2019-07-25
    by: 2019-amendment-act
    kind: inserted
    target: "sub-section (4)"
    note: "Inserted by Act 14 of 2019"
    before: "the prior text, if a substitution"
---
```

### Regulation / rule item files (`src/content/regulation-items/<set>/<num>.md`)

```yaml
---
parent: enrolment-and-update-2016  # references regulation set slug
number: "3"
title: "Biometric information required for enrolment"
chapter: "II"
status: amended
manual_edit: true
history:
  - date: 2016-09-12
    by: original
    kind: enacted
  - date: 2024-01-27
    by: enrolment-and-update-2016/2024-01-27
    kind: substituted
    before: "a resident"
    after: "an Aadhaar number holder"
---
```

### Set landing files (`src/content/regulations/<slug>.md`, `src/content/rules/<slug>.md`)

```yaml
---
title: "Aadhaar (Enrolment and Update) Regulations, 2016"
slug: enrolment-and-update-2016
made_under_sections: ["3", "23(2)(g)", "54(2)(b)"]
gazette_date: 2016-09-12
issuing_authority: UIDAI
status: in-force
source_pdf_url: "https://uidai.gov.in/images/…"
original_pdf_url: "https://web.archive.org/web/…"   # optional
original_as_of: 2016-09-12
manual_edit: true
---
```

The body of a set landing file is unused — the page generates the arrangement-of-regulations list dynamically.

### Amending regulation files (`src/content/regulation-amendments/<set>/<date>.md`)

```yaml
---
title: "The Aadhaar (Enrolment and Update) Second Amendment Regulations, 2024"
parent: enrolment-and-update-2016
gazette_date: 2024-01-27
source_pdf_url: "https://uidai.gov.in/images/…"
manual_edit: true
changes:
  - kind: inserted
    target: "regulation 2, sub-regulation (1), after clause (e)"
    after: "(f) “section” means a section of the Act"
  - kind: substituted
    target: "regulation 4, sub-regulation (1), clause (a)"
    before: "the resident"
    after: "the Aadhaar number holder"
  - kind: omitted
    target: "regulation 6, sub-regulation (3)"
    before: "the prior wording"
---

Free-form summary of the amendment goes here.
```

## Common cleanup tasks

### Removing footnote text that leaked into the body

PDFs often have footnote text like *"Subs. by Act 14 of 2019, sec. 3(i)…"* at the end of a section that the parser failed to strip. Just delete those `<p class="block …">…</p>` blocks from the body.

### Fixing OCR character substitutions

`l` ↔ `1`, `O` ↔ `0`, `rn` ↔ `m`, `cl` ↔ `d` are common confusions. Search for suspicious patterns in your editor.

### Re-flowing a paragraph

If multiple paragraphs were merged into one (e.g., `(1) text… (2) text…` on one line), split them into separate `<p class="block subsection">` blocks. The CSS handles indentation automatically.

### Adding a missing sub-clause

If the parser missed a `(i)` or `(ii)` opener, just add `<p class="block subclause">(i) text…</p>` in the right place. No re-build needed — the dev server picks it up.

### Re-attaching an amendment

If you spot a phrase that should be wrapped in `<span class="amend">` but isn't, wrap it manually with the right `data-` attributes. Click the indicator on the live site to verify the popover shows correct details.

## Workflow tips

- **Use the dev server**: `npm run dev` watches `src/content/` and reloads on save. Paste the URL in your browser, edit the file, alt-tab to verify.
- **Spot-check with `npm run build`**: catches Zod validation errors (typos in frontmatter, missing required fields).
- **`manual_edit: true` survives `npm run ingest`**: re-running the parser will skip your hand-edited file and log "skipped".
- **Bulk-flag many files**: in zsh: `for f in src/content/regulation-items/enrolment-and-update-2016/*.md; do sed -i '' '4i\
  manual_edit: true' "$f"; done` — adds the flag to every file in a set. (Verify the line number — frontmatter shape varies.)
- **Don't edit auto-generated set TOC text**: the regulation/rule set landing pages compute their TOC from the items collection, so editing the body of `src/content/regulations/<slug>.md` won't change what appears on the page (other than the metadata block).

## What lives in the source-pdfs/ tree

- `source-pdfs/act/`, `rules/`, `regulations/`, `regulation-amendments/` — the original UIDAI PDFs
- `source-pdfs/regulation-base-original/` — Wayback snapshots of the as-enacted regulations
- `source-pdfs/extracted/*.txt` — `pdftotext -layout` output, used as parser input

These files are the SOURCE OF TRUTH for the parsers. Don't edit them — edit the markdown files under `src/content/` instead.
