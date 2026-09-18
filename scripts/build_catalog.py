"""Merge canonical works and analytics into validated catalog artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.catalog import (
    GENERATOR_VERSION, build_author, build_work, catalog_entry, input_fingerprint,
    normalized_id, person_id, search_entry, validate_relations, validate_schema,
    write_if_changed,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=Path("build/canonical"))
    parser.add_argument("--analysis", type=Path, default=Path("build/analysis"))
    parser.add_argument("--output", type=Path, default=Path("build/catalog"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    canonical_paths = sorted(args.canonical.glob("*.json"))
    if not canonical_paths:
        raise SystemExit(f"No canonical documents found in {args.canonical}")
    previous_manifest_path = args.output / "build-manifest.json"
    previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8")) if previous_manifest_path.is_file() else {"inputs": {}}

    inputs: dict[str, str] = {}
    works: list[dict] = []
    author_metadata: dict[str, dict] = {}
    author_works: dict[str, list[str]] = defaultdict(list)
    reused = 0
    written = 0
    for canonical_path in canonical_paths:
        analysis_path = args.analysis / canonical_path.name
        if not analysis_path.is_file():
            raise SystemExit(f"Missing analysis artifact: {analysis_path}")
        canonical_bytes = canonical_path.read_bytes()
        analysis_bytes = analysis_path.read_bytes()
        fingerprint = input_fingerprint(canonical_bytes, analysis_bytes)
        raw_id = canonical_path.stem
        inputs[raw_id] = fingerprint
        output_path = args.output / "works" / canonical_path.name
        if previous_manifest.get("inputs", {}).get(raw_id) == fingerprint and output_path.is_file():
            work = json.loads(output_path.read_text(encoding="utf-8"))
            reused += 1
        else:
            canonical = json.loads(canonical_bytes)
            analysis = json.loads(analysis_bytes)
            work = build_work(canonical, analysis, fingerprint)
            validate_schema(work, "work.schema.json")
            _, changed = write_if_changed(output_path, work)
            written += changed
        validate_schema(work, "work.schema.json")
        works.append(work)
        metadata = work["source"]["metadata"]
        author_id = person_id(metadata["人物ID"])
        author_metadata.setdefault(author_id, metadata)
        author_works[author_id].append(work["id"])

    authors = {
        author_id: build_author(author_metadata[author_id], author_works[author_id])
        for author_id in sorted(author_metadata)
    }
    for author in authors.values():
        validate_schema(author, "author.schema.json")
        write_if_changed(args.output / "authors" / f"{author['aozora_person_id']}.json", author)
    validate_relations(works, authors)

    expected_work_files = {f"{work['aozora_work_id']}.json" for work in works}
    expected_author_files = {f"{author['aozora_person_id']}.json" for author in authors.values()}
    for path in (args.output / "works").glob("*.json"):
        if path.name not in expected_work_files:
            path.unlink()
    for path in (args.output / "authors").glob("*.json"):
        if path.name not in expected_author_files:
            path.unlink()

    entries = [catalog_entry(work, authors) for work in sorted(works, key=lambda item: item["id"])]
    catalog = {"schema_version": 1, "works": entries}
    validate_schema(catalog, "catalog.schema.json")
    write_if_changed(args.output / "indexes" / "catalog.json", catalog)
    write_if_changed(args.output / "indexes" / "authors.json", {"schema_version": 1, "authors": list(authors.values())})
    write_if_changed(args.output / "indexes" / "search.json", {"schema_version": 1, "works": [search_entry(entry) for entry in entries]})

    outputs: dict[str, str] = {}
    for path in sorted(item for item in args.output.rglob("*.json") if item.name != "build-manifest.json"):
        outputs[path.relative_to(args.output).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    corpus_fingerprint = hashlib.sha256("\n".join(f"{key}:{inputs[key]}" for key in sorted(inputs)).encode("ascii")).hexdigest()
    manifest = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "corpus_fingerprint": corpus_fingerprint,
        "inputs": inputs,
        "outputs": outputs,
    }
    validate_schema(manifest, "build-manifest.schema.json")
    write_if_changed(previous_manifest_path, manifest)
    print(f"Catalog works: {len(works)}")
    print(f"Authors:       {len(authors)}")
    print(f"Work artifacts reused:  {reused}")
    print(f"Work artifacts written: {written}")


if __name__ == "__main__":
    main()
