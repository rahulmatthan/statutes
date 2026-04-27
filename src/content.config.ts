import { defineCollection, reference, z } from "astro:content";
import { glob } from "astro/loaders";

const sections = defineCollection({
  loader: glob({ pattern: "*.md", base: "./src/content/sections" }),
  schema: z.object({
    section: z.string(),
    title: z.string(),
    chapter: z.string().optional(),
    chapter_order: z.number().optional(),
    status: z.enum(["original", "amended", "inserted", "omitted"]).default("original"),
    current_as_of: z.coerce.date().optional(),
    // Set to true to preserve hand-edits: ingest scripts will skip this file.
    manual_edit: z.boolean().optional(),
    history: z
      .array(
        z.object({
          date: z.coerce.date(),
          by: z.string(),
          kind: z.enum([
            "enacted",
            "substituted",
            "inserted",
            "omitted",
            "renumbered",
            "amended",
          ]),
          target: z.string().optional(),
          note: z.string().optional(),
          before: z.string().optional(),
          after: z.string().optional(),
        }),
      )
      .default([]),
  }),
});

const amendments = defineCollection({
  loader: glob({ pattern: "*.md", base: "./src/content/amendments" }),
  schema: z.object({
    title: z.string(),
    short_title: z.string(),
    date: z.coerce.date(),
    kind: z.enum(["act", "ordinance"]),
    source_pdf_url: z.string().url(),
    summary: z.string().optional(),
  }),
});

const rules = defineCollection({
  loader: glob({ pattern: "*.md", base: "./src/content/rules" }),
  schema: z.object({
    title: z.string(),
    short_title: z.string().optional(),
    made_under_sections: z.array(z.string()).default([]),
    gazette_date: z.coerce.date(),
    issuing_authority: z.literal("Central Government"),
    status: z.enum(["in-force", "superseded", "repealed"]).default("in-force"),
    source_pdf_url: z.string().url(),
    item_count: z.number().optional(),
    manual_edit: z.boolean().optional(),
  }),
});

const regulations = defineCollection({
  loader: glob({ pattern: "*.md", base: "./src/content/regulations" }),
  schema: z.object({
    title: z.string(),
    short_title: z.string().optional(),
    made_under_sections: z.array(z.string()).default([]),
    gazette_date: z.coerce.date(),
    issuing_authority: z.literal("UIDAI"),
    status: z.enum(["in-force", "superseded", "repealed"]).default("in-force"),
    source_pdf_url: z.string().url(),
    // Wayback link to the as-enacted (or earliest available) PDF.
    original_pdf_url: z.string().url().optional(),
    original_as_of: z.coerce.date().optional(),
    item_count: z.number().optional(),
    manual_edit: z.boolean().optional(),
  }),
});

// Per-item schemas — one file per individual rule / regulation.
const _itemHistorySchema = z
  .array(
    z.object({
      date: z.coerce.date(),
      by: z.string(),
      kind: z.enum([
        "enacted", "substituted", "inserted",
        "omitted", "renumbered", "amended",
      ]),
      target: z.string().optional(),
      note: z.string().optional(),
      before: z.string().optional(),
      after: z.string().optional(),
    }),
  )
  .default([]);

const ruleItems = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/rule-items" }),
  schema: z.object({
    parent: reference("rules"),
    number: z.string(),
    title: z.string(),
    chapter: z.string().optional(),
    chapter_order: z.number().optional(),
    status: z.enum(["original", "amended", "inserted", "omitted"]).default("original"),
    current_as_of: z.coerce.date().optional(),
    history: _itemHistorySchema,
    manual_edit: z.boolean().optional(),
  }),
});

const regulationItems = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/regulation-items" }),
  schema: z.object({
    parent: reference("regulations"),
    number: z.string(),
    title: z.string(),
    chapter: z.string().optional(),
    chapter_order: z.number().optional(),
    status: z.enum(["original", "amended", "inserted", "omitted"]).default("original"),
    current_as_of: z.coerce.date().optional(),
    history: _itemHistorySchema,
    manual_edit: z.boolean().optional(),
  }),
});

// As-enacted snapshots of individual regulations, sourced from Wayback Machine
// archives of the original publications. One file per regulation per set.
const regulationItemsOriginal = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/regulation-items-original" }),
  schema: z.object({
    parent: reference("regulations"),
    number: z.string(),
    title: z.string(),
    chapter: z.string().optional(),
    as_of: z.coerce.date(),
    manual_edit: z.boolean().optional(),
  }),
});

const regulationAmendments = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/regulation-amendments" }),
  schema: z.object({
    title: z.string(),
    parent: reference("regulations"),
    gazette_date: z.coerce.date(),
    source_pdf_url: z.string().url(),
    changes: z
      .array(
        z.object({
          target: z.string().optional(),
          kind: z.enum(["substituted", "inserted", "omitted", "renumbered"]),
          note: z.string().optional(),
          before: z.string().optional(),
          after: z.string().optional(),
        }),
      )
      .default([]),
    manual_edit: z.boolean().optional(),
  }),
});

export const collections = {
  sections,
  amendments,
  rules,
  ruleItems,
  regulations,
  regulationItems,
  regulationItemsOriginal,
  regulationAmendments,
};
