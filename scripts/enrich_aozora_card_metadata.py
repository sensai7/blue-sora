"""Fill missing reduced-corpus metadata from Aozora Bunko card pages.

This is intended for works downloaded from card pages that postdate the local
``aozora.csv`` snapshot. By default it updates only rows without an Aozora
release date, leaving established CSV metadata untouched.
"""

from __future__ import annotations

import argparse
import csv
import re
from html.parser import HTMLParser
from pathlib import Path
from time import sleep
from urllib.request import Request, urlopen


USER_AGENT = "blue-sora-aozora-metadata/1.0"
FIELD_MAP = {
    "作品名読み": "作品名読み",
    "初出": "初出",
    "文字遣い種別": "文字遣い種別",
    "底本": "底本名1",
    "出版社": "底本出版社名1",
    "初版発行日": "底本初版発行年1",
    "入力に使用": "入力に使用した版1",
    "校正に使用": "校正に使用した版1",
    "底本の親本": "底本の親本名1",
    "入力": "入力者",
    "校正": "校正者",
}


class CardTableParser(HTMLParser):
    """Collect label/value pairs from all card-page table rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_row = False
        self._cell_depth = 0
        self._cell_parts: list[str] = []
        self._cells: list[str] = []
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._in_row = True
            self._cells = []
        elif tag in {"td", "th"} and self._in_row:
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_depth:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell_depth:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(" ".join("".join(self._cell_parts).split()))
        elif tag == "tr" and self._in_row:
            if len(self._cells) >= 2:
                label = self._cells[0].rstrip("：:").strip()
                value = " ".join(self._cells[1:]).strip()
                if label and value:
                    self.values[label] = value
            self._in_row = False


def decode_html(payload: bytes) -> str:
    match = re.search(rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_-]+)", payload[:4096], re.IGNORECASE)
    encodings = [match.group(1).decode("ascii")] if match else []
    encodings.extend(["utf-8", "cp932"])
    for encoding in dict.fromkeys(encodings):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            pass
    return payload.decode("utf-8", errors="replace")


def fetch_card(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return decode_html(response.read())


def card_fields(html: str) -> dict[str, str]:
    parser = CardTableParser()
    parser.feed(html)
    parser.close()
    fields = {target: parser.values[label] for label, target in FIELD_MAP.items() if parser.values.get(label)}
    xhtml_details = parser.values.get("XHTMLファイル", "")
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", xhtml_details)
    if dates:
        fields["公開日"] = dates[0]
    if len(dates) > 1:
        fields["最終更新日"] = dates[-1]
    return fields


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("reduced_aozora.csv"))
    parser.add_argument("--work-id", action="append", help="Update one six-digit work ID; may be repeated.")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between card requests (default: 1).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.metadata.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise SystemExit(f"No header in {args.metadata}")
        fieldnames = reader.fieldnames
        rows = list(reader)

    selected = set(args.work_id or [])
    candidates = [
        row for row in rows
        if row.get("図書カードURL") and (row["作品ID"].zfill(6) in selected if selected else not row.get("公開日"))
    ]
    updated = 0
    for index, row in enumerate(candidates):
        if index:
            sleep(args.delay)
        work_id = row["作品ID"].zfill(6)
        try:
            fields = card_fields(fetch_card(row["図書カードURL"]))
            if not fields:
                print(f"SKIP {work_id}: no card table metadata found")
                continue
            row.update(fields)
            updated += 1
            print(f"UPDATED {work_id}: {len(fields)} metadata fields")
        except OSError as error:
            print(f"ERROR {work_id}: {error}")

    with args.metadata.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated works: {updated}/{len(candidates)}")


if __name__ == "__main__":
    main()
