"""Remove works marked as copyrighted from an Aozora corpus and metadata CSV.

The command is a dry run unless ``--apply`` is supplied. Work IDs are removed
as a unit so translated or edited works with multiple contributor rows cannot
leave partial metadata behind.
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from collections import defaultdict
from pathlib import Path


COPYRIGHT_FLAG_COLUMN = "作品著作権フラグ"
WORK_ID_COLUMN = "作品ID"
PROTECTED_VALUE = "あり"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("aozora.csv"))
    parser.add_argument("--corpus", type=Path, default=Path("aozora_corpus"))
    parser.add_argument("--apply", action="store_true", help="Perform the removal; otherwise only report it")
    return parser.parse_args()


def load_metadata(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames is None:
            raise ValueError(f"Metadata has no header: {path}")
        required = {WORK_ID_COLUMN, COPYRIGHT_FLAG_COLUMN}
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing required CSV columns: {sorted(missing)}")
        return reader.fieldnames, list(reader)


def protected_work_ids(rows: list[dict[str, str]]) -> set[str]:
    rows_by_work: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        rows_by_work[row[WORK_ID_COLUMN].zfill(6)].append(row)

    inconsistent = {
        work_id
        for work_id, work_rows in rows_by_work.items()
        if len({row[COPYRIGHT_FLAG_COLUMN] for row in work_rows}) != 1
    }
    if inconsistent:
        examples = ", ".join(sorted(inconsistent)[:10])
        raise ValueError(f"Inconsistent work-level copyright flags for: {examples}")

    return {
        work_id
        for work_id, work_rows in rows_by_work.items()
        if work_rows[0][COPYRIGHT_FLAG_COLUMN] == PROTECTED_VALUE
    }


def validate_corpus_path(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"Corpus directory does not exist: {resolved}")
    if resolved == Path(resolved.anchor) or resolved == Path.cwd().resolve():
        raise ValueError(f"Refusing broad corpus target: {resolved}")
    return resolved


def write_filtered_metadata(
    destination: Path,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    excluded_ids: set[str],
) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8-sig",
        newline="",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(
                row for row in rows if row[WORK_ID_COLUMN].zfill(6) not in excluded_ids
            )
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def main() -> None:
    args = parse_args()
    metadata = args.metadata.resolve()
    corpus = validate_corpus_path(args.corpus)
    fieldnames, rows = load_metadata(metadata)
    excluded_ids = protected_work_ids(rows)
    protected_rows = [
        row for row in rows if row[WORK_ID_COLUMN].zfill(6) in excluded_ids
    ]
    files = [corpus / f"{work_id}.html" for work_id in sorted(excluded_ids)]
    existing_files = [path for path in files if path.is_file()]

    print(f"Protected work IDs:    {len(excluded_ids)}")
    print(f"Metadata rows removed: {len(protected_rows)}")
    print(f"HTML files removed:    {len(existing_files)}")
    print(f"HTML files not present:{len(files) - len(existing_files):>5}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to perform the removal.")
        return

    temporary_metadata = write_filtered_metadata(metadata, fieldnames, rows, excluded_ids)
    staging = Path(tempfile.mkdtemp(prefix=".copyright-removal-", dir=corpus)).resolve()
    if staging.parent != corpus:
        temporary_metadata.unlink(missing_ok=True)
        raise RuntimeError(f"Unsafe staging location: {staging}")

    staged: list[tuple[Path, Path]] = []
    try:
        for source in existing_files:
            target = staging / source.name
            source.replace(target)
            staged.append((source, target))
        os.replace(temporary_metadata, metadata)
    except Exception:
        for source, target in reversed(staged):
            if target.exists() and not source.exists():
                target.replace(source)
        temporary_metadata.unlink(missing_ok=True)
        staging.rmdir()
        raise

    for _, target in staged:
        target.unlink()
    staging.rmdir()
    print("Removal complete.")


if __name__ == "__main__":
    main()
