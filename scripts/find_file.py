#!/usr/bin/env python3
"""Print the source file path for a given URL or slug.

Usage:
    python3 scripts/find_file.py /act/s/3
    python3 scripts/find_file.py /regulations/payment-of-fees-2023/r/5
    python3 scripts/find_file.py payment-of-fees-2023/5      # accepts trimmed form

If the matching file exists, the absolute path is printed; otherwise the
expected path is printed with a `(missing)` marker.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "src/content"


def resolve(url: str) -> list[tuple[Path, str]]:
    """Return one or more candidate (path, label) for the URL."""
    u = url.strip().rstrip("/")
    if u.startswith("http://") or u.startswith("https://"):
        # Take only the path portion.
        u = "/" + "/".join(u.split("/", 3)[3:])
    if not u.startswith("/"):
        u = "/" + u

    # /act/s/<num>
    m = re.match(r"^/act/s/([\w]+)$", u)
    if m:
        return [(CONTENT / f"sections/s-{m.group(1).lower()}.md", "section")]

    # /regulations/<set>/r/<num>
    m = re.match(r"^/regulations/([^/]+)/r/([\w]+)$", u)
    if m:
        return [
            (CONTENT / f"regulation-items/{m.group(1)}/{m.group(2).lower()}.md", "current text"),
            (CONTENT / f"regulation-items-original/{m.group(1)}/{m.group(2).lower()}.md", "as-enacted text"),
        ]

    # /regulations/<set>/a/<date>
    m = re.match(r"^/regulations/([^/]+)/a/([\d-]+)$", u)
    if m:
        return [(CONTENT / f"regulation-amendments/{m.group(1)}/{m.group(2)}.md", "amending instrument")]

    # /regulations/<set>
    m = re.match(r"^/regulations/([^/]+)$", u)
    if m:
        return [(CONTENT / f"regulations/{m.group(1)}.md", "regulation set landing")]

    # /rules/<set>/r/<num>
    m = re.match(r"^/rules/([^/]+)/r/([\w]+)$", u)
    if m:
        return [(CONTENT / f"rule-items/{m.group(1)}/{m.group(2).lower()}.md", "rule")]

    # /rules/<set>
    m = re.match(r"^/rules/([^/]+)$", u)
    if m:
        return [(CONTENT / f"rules/{m.group(1)}.md", "rule set landing")]

    # /amendments/<slug>
    m = re.match(r"^/amendments/([^/]+)$", u)
    if m:
        return [(CONTENT / f"amendments/{m.group(1)}.md", "amending Act / Ordinance")]

    # Trimmed forms — accept "<set>/<num>" as a shortcut for regulation items.
    m = re.match(r"^/?([^/]+)/(\d+[a-z]?)$", u)
    if m:
        return [
            (CONTENT / f"regulation-items/{m.group(1)}/{m.group(2).lower()}.md", "current text"),
            (CONTENT / f"regulation-items-original/{m.group(1)}/{m.group(2).lower()}.md", "as-enacted text"),
        ]

    return []


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    candidates = resolve(sys.argv[1])
    if not candidates:
        print(f"no file mapping known for: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    for path, label in candidates:
        if path.exists():
            print(f"{path}  ({label})")
        else:
            print(f"{path}  ({label}, missing)")


if __name__ == "__main__":
    main()
