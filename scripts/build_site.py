"""Build the Blue Sora static site from catalog artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.site import build_site
from blue_sora.epub import build_epubs
from blue_sora.pdf import build_pdfs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("build/catalog"))
    parser.add_argument("--output", type=Path, default=Path("build/site"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    epub_result = build_epubs(args.catalog, args.output)
    print(f"EPUBs generated: {epub_result['generated']}")
    print(f"EPUBs unchanged: {epub_result['unchanged']}")
    print(f"EPUB failures: {epub_result['failed']}")
    pdf_result = build_pdfs(args.catalog, args.output)
    print(f"PDFs generated: {pdf_result['generated']}")
    print(f"PDFs unchanged: {pdf_result['unchanged']}")
    print(f"PDF failures: {pdf_result['failed']}")
    result = build_site(args.catalog, args.output)
    print(f"Generated pages: {result['pages']}")
    print(f"Pages rewritten: {result['written']}")
    print(f"Catalog works available: {result['works']}")
    print(f"Fingerprinted assets: {result['assets']}")
    print(f"Local work media: {result['media']}")
    if epub_result["failed"] or pdf_result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
