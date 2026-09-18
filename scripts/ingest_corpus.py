"""Build deterministic canonical JSON documents from an Aozora corpus."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.ingestion import download_assets, ingest_work


def load_metadata(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return {row["作品ID"].zfill(6): row for row in csv.DictReader(source)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("reduced_corpus"))
    parser.add_argument("--metadata", type=Path, default=Path("reduced_aozora.csv"))
    parser.add_argument("--output", type=Path, default=Path("build/canonical"))
    parser.add_argument("--download-assets", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = load_metadata(args.metadata)
    args.output.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for path in sorted(args.corpus.glob("*.html")):
        row = metadata.get(path.stem)
        if row is None:
            failures.append(f"{path.name}: missing metadata")
            continue
        source_url = row.get("XHTML/HTMLファイルURL", "")
        document = ingest_work(path.read_bytes(), row, source_filename=path.name, source_url=source_url)
        if args.download_assets:
            download_assets(document, args.output)
        destination = args.output / f"{path.stem}.json"
        destination.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"{path.stem}: {len(document['assets'])} assets, {len(document['warnings'])} warnings")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
