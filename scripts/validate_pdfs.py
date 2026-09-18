"""Validate every generated PDF for structure, embedded fonts, text, and images."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.pdf import validate_pdf, visible_text


def count_node_type(value: object, node_type: str) -> int:
    if isinstance(value, list):
        return sum(count_node_type(item, node_type) for item in value)
    if isinstance(value, dict):
        return int(value.get("type") == node_type) + sum(count_node_type(item, node_type) for item in value.values())
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("build/catalog"))
    parser.add_argument("--site", type=Path, default=Path("build/site"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = json.loads((args.catalog / "indexes" / "catalog.json").read_text(encoding="utf-8"))
    total_pages = 0
    total_fonts = 0
    total_images = 0
    work_records = []
    for work in catalog["works"]:
        raw_id = work["id"].rsplit(":", 1)[-1]
        record = json.loads((args.catalog / "works" / f"{raw_id}.json").read_text(encoding="utf-8"))
        work_records.append(record)
        path = args.site / "downloads" / f'{work["slug"]}.pdf'
        if not path.is_file():
            raise SystemExit(f"Missing PDF: {path}")
        result = validate_pdf(path, record)
        total_pages += result["pages"]
        total_fonts += result["fonts"]
        total_images += result["images"]
    short = min(work_records, key=lambda item: item["analytics"]["metrics"]["length_words"])
    long = max(work_records, key=lambda item: item["analytics"]["metrics"]["length_words"])
    illustrated = next((item for item in work_records if any(asset["kind"] == "illustration" for asset in item["assets"])), None)
    ruby_heavy = max(work_records, key=lambda item: count_node_type(item["content"]["body"], "ruby"))
    if illustrated is None or not visible_text(ruby_heavy["content"]["body"]):
        raise SystemExit("Representative PDF fixtures are incomplete")
    print(f"Validated PDFs: {len(catalog['works'])}")
    print(f"Validated pages: {total_pages}")
    print(f"Embedded font resources: {total_fonts}")
    print(f"Embedded canonical images: {total_images}")
    print(f"Short representative: {short['slug']}")
    print(f"Long representative: {long['slug']}")
    print(f"Illustrated representative: {illustrated['slug']}")
    print(f"Ruby-heavy representative: {ruby_heavy['slug']}")


if __name__ == "__main__":
    main()
