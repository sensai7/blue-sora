"""Build the small Aozora Bunko corpus used during development.

The metadata CSV is UTF-8 with a BOM.  The HTML documents themselves are
copied byte-for-byte so their original Shift-JIS/JIS X 0208 encoding is not
accidentally changed.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import Counter
from pathlib import Path


DEFAULT_AUTHORS = ("江戸川乱歩", "福沢諭吉", "樋口夏子", "樋口一葉")


def normalized_name(row: dict[str, str]) -> str:
    return "".join((row.get("姓", ""), row.get("名", ""))).replace(" ", "").replace("　", "")


def build_reduced_corpus(
    metadata_path: Path,
    corpus_dir: Path,
    output_dir: Path,
    output_metadata: Path,
    authors: set[str],
) -> tuple[int, int, Counter[str]]:
    with metadata_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"Metadata has no header: {metadata_path}")
        required = {"作品ID", "姓", "名", "役割フラグ"}
        missing_columns = required.difference(reader.fieldnames)
        if missing_columns:
            raise ValueError(f"Missing required CSV columns: {sorted(missing_columns)}")
        selected = [
            row
            for row in reader
            if row.get("役割フラグ") == "著者" and normalized_name(row) in authors
        ]
        fieldnames = reader.fieldnames

    output_dir.mkdir(parents=True, exist_ok=True)
    copied_ids: set[str] = set()
    included_rows: list[dict[str, str]] = []
    missing_files: list[tuple[str, str]] = []

    for row in selected:
        work_id = row["作品ID"].zfill(6)
        source_file = corpus_dir / f"{work_id}.html"
        if not source_file.is_file():
            missing_files.append((work_id, row.get("作品名", "")))
            continue
        if work_id not in copied_ids:
            shutil.copy2(source_file, output_dir / source_file.name)
            copied_ids.add(work_id)
        included_rows.append(row)

    output_metadata.parent.mkdir(parents=True, exist_ok=True)
    with output_metadata.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(included_rows)

    by_author = Counter(normalized_name(row) for row in included_rows)
    print(f"Selected metadata rows: {len(selected)}")
    print(f"Copied HTML works:     {len(copied_ids)}")
    print(f"Written CSV rows:      {len(included_rows)}")
    for author, count in sorted(by_author.items()):
        print(f"  {author}: {count}")
    if missing_files:
        print(f"Skipped missing HTML:  {len(missing_files)}")
        for work_id, title in missing_files:
            print(f"  {work_id}: {title}")
    return len(copied_ids), len(missing_files), by_author


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("aozora.csv"))
    parser.add_argument("--corpus", type=Path, default=Path("aozora_corpus"))
    parser.add_argument("--output-dir", type=Path, default=Path("reduced_corpus"))
    parser.add_argument("--output-metadata", type=Path, default=Path("reduced_aozora.csv"))
    parser.add_argument("--author", action="append", dest="authors", help="Exact Japanese author name; repeat as needed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    authors = set(args.authors or DEFAULT_AUTHORS)
    build_reduced_corpus(args.metadata, args.corpus, args.output_dir, args.output_metadata, authors)


if __name__ == "__main__":
    main()
