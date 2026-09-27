"""Add downloaded Aozora XHTML files to the reduced Blue Sora corpus.

Files must use the scraper naming convention:
``<person-id>_<work-id>_<revision-id>.html``.  The script copies each file as
``<work-id>.html`` and creates metadata from an existing row for that author.
This supports Aozora works that are newer than the checked-in metadata CSV.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path


SCRAPED_NAME = re.compile(r"^(?P<person>\d{6})_(?P<work>\d+)_(?P<revision>\d+)\.html$")
PERSON_COLUMNS = {
    "人物ID", "姓", "名", "姓読み", "名読み", "姓読みソート用", "名読みソート用",
    "姓ローマ字", "名ローマ字", "役割フラグ", "生年月日", "没年月日", "人物著作権フラグ",
}


class TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._title_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1" and "title" in (dict(attrs).get("class") or "").split():
            self._title_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._title_depth:
            self._title_depth = 0

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self._parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self._parts).strip()


def source_title(path: Path) -> str:
    parser = TitleParser()
    parser.feed(path.read_text(encoding="cp932", errors="replace"))
    parser.close()
    if not parser.title:
        raise ValueError(f"Could not find h1.title in {path}")
    return parser.title


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f"No header in {path}")
        return reader.fieldnames, list(reader)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scraped", type=Path, default=Path("scraped"))
    parser.add_argument("--corpus", type=Path, default=Path("reduced_corpus"))
    parser.add_argument("--metadata", type=Path, default=Path("reduced_aozora.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fieldnames, rows = load_csv(args.metadata)
    templates = {
        row["人物ID"].zfill(6): row
        for row in rows
        if row.get("人物ID") and row.get("役割フラグ") == "著者"
    }
    existing = {row["作品ID"].zfill(6) for row in rows if row.get("作品ID")}
    additions: list[dict[str, str]] = []
    args.corpus.mkdir(parents=True, exist_ok=True)

    for source in sorted(args.scraped.glob("*.html")):
        match = SCRAPED_NAME.fullmatch(source.name)
        if not match:
            print(f"SKIP {source.name}: unexpected filename")
            continue
        person_id = match["person"]
        work_id = match["work"].zfill(6)
        if work_id in existing:
            print(f"SKIP {source.name}: {work_id} already in metadata")
            continue
        template = templates.get(person_id)
        if template is None:
            raise SystemExit(f"No author metadata template for person {person_id}")
        target = args.corpus / f"{work_id}.html"
        shutil.copy2(source, target)
        row = {key: "" for key in fieldnames}
        row.update({key: template.get(key, "") for key in PERSON_COLUMNS})
        row.update({
            "作品ID": work_id,
            "作品名": source_title(source),
            "作品名読み": "",
            "ソート用読み": "",
            "副題": "",
            "副題読み": "",
            "原題": "",
            "初出": "",
            "分類番号": "",
            "文字遣い種別": "",
            "作品著作権フラグ": "",
            "公開日": "",
            "最終更新日": "",
            "図書カードURL": f"https://www.aozora.gr.jp/cards/{person_id}/card{int(match['work'])}.html",
            "XHTML/HTMLファイルURL": (
                f"https://www.aozora.gr.jp/cards/{person_id}/files/"
                f"{match['work']}_{match['revision']}.html"
            ),
        })
        additions.append(row)
        existing.add(work_id)
        print(f"ADDED {work_id}.html - {row['作品名']}")

    if additions:
        with args.metadata.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows + additions)
    print(f"Integrated works: {len(additions)}")


if __name__ == "__main__":
    main()
