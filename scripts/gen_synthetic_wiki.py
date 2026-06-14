#!/usr/bin/env python3
"""Generate a synthetic wiki for graph performance testing (#194).

Writes N pages with ~M total ``[[wikilinks]]`` into a brain's ``wiki/``
directory so the graph view can be exercised at scale. Not a product feature —
a developer fixture.

Usage:
    python scripts/gen_synthetic_wiki.py <brain_dir> [pages] [links_per_page]
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

TYPES = ["concept", "entity", "synthesis", "decision", "research", "project"]


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    brain = Path(sys.argv[1])
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    per_page = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    random.seed(42)

    out = brain / "wiki" / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    titles = [f"Synthetic Page {i:04d}" for i in range(pages)]

    for i, title in enumerate(titles):
        ptype = TYPES[i % len(TYPES)]
        targets = random.sample(
            [t for j, t in enumerate(titles) if j != i],
            k=min(per_page, pages - 1),
        )
        links = "\n".join(f"- [[{t}]]" for t in targets)
        tag = f"cluster-{i % 12}"
        body = (
            f"---\n"
            f"title: {title}\n"
            f"type: {ptype}\n"
            f"tags: [{tag}]\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"Synthetic page for graph scale testing. Related:\n\n{links}\n"
        )
        (out / f"synthetic-page-{i:04d}.md").write_text(body, encoding="utf-8")

    print(f"Wrote {pages} pages (~{pages * per_page} links) to {out}")


if __name__ == "__main__":
    main()
