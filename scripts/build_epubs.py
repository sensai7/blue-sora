"""Generate deterministic EPUB 3 downloads for every catalog work."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.epub import build_epubs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("build/catalog"))
    parser.add_argument("--output", type=Path, default=Path("build/site"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_epubs(args.catalog, args.output)
    print(f"Catalog works: {result['works']}")
    print(f"EPUBs generated: {result['generated']}")
    print(f"EPUBs unchanged: {result['unchanged']}")
    print(f"EPUB failures: {result['failed']}")
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
