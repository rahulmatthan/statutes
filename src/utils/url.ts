// Path helper for the deploy base. The Astro `base` config (e.g. `/statutes`)
// is exposed via `import.meta.env.BASE_URL` (always with a trailing slash).
// Use `url("/act")` for absolute internal links — works in dev (base "/")
// and in production (base "/statutes/").

const RAW_BASE = import.meta.env.BASE_URL ?? "/";
const BASE = RAW_BASE.replace(/\/$/, ""); // no trailing slash

export function url(path: string): string {
  if (!path.startsWith("/")) path = `/${path}`;
  return `${BASE}${path}`;
}

export const baseUrl = BASE;
