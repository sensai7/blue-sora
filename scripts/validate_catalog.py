"""Validate Milestone 4 catalog schemas, relations, and artifact hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.catalog import validate_relations, validate_schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("build/catalog"))
    parser.add_argument("--expected-works", type=int, default=126)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = args.catalog / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_schema(manifest, "build-manifest.schema.json")

    works = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((args.catalog / "works").glob("*.json"))]
    authors = {
        author["id"]: author
        for author in [json.loads(path.read_text(encoding="utf-8")) for path in sorted((args.catalog / "authors").glob("*.json"))]
    }
    if len(works) != args.expected_works:
        raise SystemExit(f"Expected {args.expected_works} works, found {len(works)}")
    for work in works:
        validate_schema(work, "work.schema.json")
    for author in authors.values():
        validate_schema(author, "author.schema.json")
    validate_relations(works, authors)

    catalog = json.loads((args.catalog / "indexes" / "catalog.json").read_text(encoding="utf-8"))
    validate_schema(catalog, "catalog.schema.json")
    if {entry["id"] for entry in catalog["works"]} != {work["id"] for work in works}:
        raise SystemExit("Catalog index and work-detail artifacts do not match")
    search = json.loads((args.catalog / "indexes" / "search.json").read_text(encoding="utf-8"))
    if {entry["id"] for entry in search["works"]} != {work["id"] for work in works}:
        raise SystemExit("Search index and work-detail artifacts do not match")

    for relative_path, expected_hash in manifest["outputs"].items():
        path = args.catalog / relative_path
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise SystemExit(f"Missing or changed artifact: {relative_path}")

    print(f"Validated works:   {len(works)}")
    print(f"Validated authors: {len(authors)}")
    print(f"Validated outputs: {len(manifest['outputs'])}")
    print("Broken relations:  0")
    print("Artifact hash failures: 0")


if __name__ == "__main__":
    main()
