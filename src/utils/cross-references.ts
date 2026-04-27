import { getCollection } from "astro:content";

export type SectionRef = string;

function normalizeSectionRef(s: string): SectionRef {
  return s.replace(/\s+/g, "").toLowerCase();
}

export function sectionMatches(needle: string, haystack: string): boolean {
  const a = normalizeSectionRef(needle);
  const b = normalizeSectionRef(haystack);
  if (a === b) return true;
  // a regulation cited as "23(2)(g)" applies to section 23 too
  if (b.startsWith(a + "(")) return true;
  return false;
}

export async function getRulesUnderSection(section: string) {
  const rules = await getCollection("rules");
  return rules.filter((r) =>
    r.data.made_under_sections.some((s) => sectionMatches(section, s)),
  );
}

export async function getRegulationsUnderSection(section: string) {
  const regs = await getCollection("regulations");
  return regs.filter((r) =>
    r.data.made_under_sections.some((s) => sectionMatches(section, s)),
  );
}

export async function getAmendmentsForRegulation(parentSlug: string) {
  const amendments = await getCollection("regulationAmendments");
  return amendments
    .filter((a) => a.data.parent.id === parentSlug)
    .sort(
      (a, b) =>
        a.data.gazette_date.getTime() - b.data.gazette_date.getTime(),
    );
}

export function sectionIdToParam(id: string): string {
  // file id "s-3a" -> URL param "3a"
  return id.replace(/^s-/, "");
}

export function sectionDisplay(section: string): string {
  return section.toUpperCase().replace(/^([0-9]+)([A-Z]+)$/, "$1$2");
}
