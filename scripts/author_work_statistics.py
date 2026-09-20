"""Print Aozora catalogue work counts by author."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import unicodedata


PLACEHOLDER_AUTHORS = """夏目漱石
森鴎外
芥川竜之介
太宰治
宮沢賢治
樋口一葉
泉鏡花
国木田独歩
田山花袋
徳田秋声
永井荷風
有島武郎
島崎藤村
谷崎潤一郎
横光利一
梶井基次郎
中島敦
坂口安吾
織田作之助
堀辰雄
林芙美子
宮本百合子
岡本かの子
与謝野晶子
石川啄木
正岡子規
萩原朔太郎
中原中也
高村光太郎
室生犀星
斎藤茂吉
北原白秋
幸田露伴
二葉亭四迷
坪内逍遥
江戸川乱歩
夢野久作
岡本綺堂
菊池寛
吉川英治
山本周五郎
小川未明
新美南吉
寺田寅彦
紫式部
福沢諭吉
上田敏
北村透谷
折口信夫
小泉八雲"""


@dataclass(frozen=True)
class AuthorStats:
    author: str
    catalogued_works: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("../aozora.csv"))
    parser.add_argument(
        "--authors-file",
        type=Path,
        help="UTF-8 text file containing one author name per line. Uses the placeholder list by default.",
    )
    parser.add_argument(
        "--work-limit",
        type=int,
        default=30,
        help="Print authors with fewer works than this limit after the table (default: 30).",
    )
    return parser.parse_args()


def read_authors(path: Path | None) -> list[str]:
    text = path.read_text(encoding="utf-8") if path else PLACEHOLDER_AUTHORS
    return [line.strip() for line in text.splitlines() if line.strip()]


def collect_work_authors(metadata_path: Path, requested: set[str]) -> dict[str, set[str]]:
    """Return requested credited authors for every unique catalogue work ID."""
    work_authors: dict[str, set[str]] = defaultdict(set)
    with metadata_path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("役割フラグ") != "著者":
                continue
            author = f"{row.get('姓', '')}{row.get('名', '')}"
            if author in requested:
                work_authors[row["作品ID"].zfill(6)].add(author)
    return work_authors


def summarize(authors: list[str], metadata_path: Path) -> list[AuthorStats]:
    work_authors = collect_work_authors(metadata_path, set(authors))
    catalogued = defaultdict(int)

    for credited_authors in work_authors.values():
        for author in credited_authors:
            catalogued[author] += 1

    return [
        AuthorStats(
            author=author,
            catalogued_works=catalogued[author],
        )
        for author in authors
    ]


def print_table(stats: list[AuthorStats]) -> None:
    headers = ("Author", "Works (CSV)")
    rows = [(item.author, f"{item.catalogued_works:,}") for item in stats]
    widths = [max(display_width(header), *(display_width(row[index]) for row in rows)) for index, header in enumerate(headers)]
    divider = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    print(divider)
    print("| " + " | ".join(pad(header, width) for header, width in zip(headers, widths)) + " |")
    print(divider)
    for row in rows:
        print("| " + " | ".join(pad(value, width) for value, width in zip(row, widths)) + " |")
    print(divider)


def print_authors_below_work_limit(stats: list[AuthorStats], work_limit: int = 30) -> None:
    """Print authors whose catalogued corpus has fewer works than ``work_limit``."""
    authors = [item.author for item in stats if item.catalogued_works < work_limit]
    print(f"Authors with fewer than {work_limit} works:")
    for author in authors:
        print(author)


def display_width(value: str) -> int:
    """Approximate terminal width, treating Japanese full-width characters as two cells."""
    return sum(2 if unicodedata.east_asian_width(character) in {"F", "W", "A"} else 1 for character in value)


def pad(value: str, width: int) -> str:
    return value + " " * (width - display_width(value))


def main() -> None:
    args = parse_args()
    if not args.metadata.is_file():
        raise SystemExit(f"Metadata CSV not found: {args.metadata}")
    stats = summarize(read_authors(args.authors_file), args.metadata)
    print_table(stats)
    print_authors_below_work_limit(stats, args.work_limit)


if __name__ == "__main__":
    main()
