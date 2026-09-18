"""Validate every Milestone 2 canonical-ingestion acceptance invariant."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.ingestion import render_blocks


REMOTE_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']https?://", re.IGNORECASE)


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("reduced_corpus"))
    parser.add_argument("--canonical", type=Path, default=Path("build/canonical"))
    parser.add_argument("--expected-works", type=int, default=126)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_ids = {path.stem for path in args.corpus.glob("*.html")}
    document_paths = sorted(args.canonical.glob("*.json"))
    document_ids = {path.stem for path in document_paths}
    if len(document_paths) != args.expected_works or source_ids != document_ids:
        raise SystemExit(
            f"Document set mismatch: {len(source_ids)} source works, "
            f"{len(document_paths)} canonical documents"
        )

    references = 0
    unique_assets: set[str] = set()
    for path in document_paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["warnings"]:
            raise SystemExit(f"{path.name}: {len(document['warnings'])} unresolved warnings")
        asset_ids = {asset["id"] for asset in document["assets"]}
        for asset in document["assets"]:
            references += 1
            unique_assets.add(asset["local_path"])
            local_path = args.canonical / asset["local_path"]
            if asset["status"] != "stored":
                raise SystemExit(f"{path.name}: asset {asset['id']} is {asset['status']}")
            if not local_path.is_file() or digest(local_path) != asset["sha256"]:
                raise SystemExit(f"{path.name}: missing or invalid asset {asset['id']}")

        for node in walk(document["content"]):
            if node.get("type") in {"illustration", "gaiji"}:
                if node.get("asset_id") not in asset_ids:
                    raise SystemExit(f"{path.name}: unresolved content asset reference")
                if any(key in node for key in {"src", "url", "original_url"}):
                    raise SystemExit(f"{path.name}: remote image data leaked into canonical content")

        for section in document["content"].values():
            if REMOTE_IMAGE_RE.search(render_blocks(section, document["assets"])):
                raise SystemExit(f"{path.name}: rendered content contains a remote image")

    print(f"Canonical documents:    {len(document_paths)}")
    print("Unresolved diagnostics: 0")
    print(f"Stored asset references:{references:>5}")
    print(f"Unique cached assets:   {len(unique_assets):>5}")
    print("Asset checksum failures: 0")
    print("Remote image dependencies: 0")


if __name__ == "__main__":
    main()
