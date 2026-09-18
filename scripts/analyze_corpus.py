"""Print quality-control statistics for an Aozora HTML corpus."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


KANJI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヶ]")
KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ffー]")
SENTENCE_RE = re.compile(r"[^。！？!?]+[。！？!?]?")


class AozoraTextParser(HTMLParser):
    """Extract visible content, preferring Aozora's main_text container."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._main_depth = 0
        self._saw_main = False
        self._all_text: list[str] = []
        self._main_text: list[str] = []
        self.paragraphs = 0
        self.headings = 0
        self.ruby = 0
        self.images = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag in {"head", "script", "style"}:
            self._ignored_depth += 1
        if tag == "div" and "main_text" in classes:
            self._saw_main = True
            self._main_depth = 1
        elif tag == "div" and self._main_depth:
            self._main_depth += 1
        if not self._main_depth:
            return
        if tag == "p":
            self.paragraphs += 1
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} or any("midashi" in c for c in classes):
            self.headings += 1
        elif tag == "ruby":
            self.ruby += 1
        elif tag == "img":
            self.images += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._main_depth:
            self._main_depth -= 1
        if tag in {"head", "script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        self._all_text.append(data)
        if self._main_depth:
            self._main_text.append(data)

    @property
    def text(self) -> str:
        return "".join(self._main_text if self._saw_main else self._all_text)


@dataclass(frozen=True)
class WorkStats:
    work_id: str
    title: str
    author: str
    file_bytes: int
    characters: int
    kanji: int
    unique_kanji: int
    kana: int
    sentences: int
    average_sentence_length: float
    paragraphs: int
    headings: int
    ruby: int
    images: int


def read_shift_jis(path: Path) -> str:
    # CP932 is Shift-JIS compatible and also accepts the vendor extensions that
    # occur in a small number of historical Aozora files.
    return path.read_text(encoding="cp932", errors="replace")


def visible_length(text: str) -> int:
    return sum(not char.isspace() for char in text)


def metadata_by_id(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    return {row["作品ID"].zfill(6): row for row in rows}


def analyze_work(path: Path, metadata: dict[str, str]) -> WorkStats:
    parser = AozoraTextParser()
    parser.feed(read_shift_jis(path))
    text = parser.text
    sentences = [part for part in SENTENCE_RE.findall(text) if visible_length(part)]
    sentence_lengths = [visible_length(part) for part in sentences]
    kanji_chars = KANJI_RE.findall(text)
    return WorkStats(
        work_id=path.stem,
        title=metadata.get("作品名", "(unknown title)"),
        author=(metadata.get("姓", "") + metadata.get("名", "")) or "(unknown author)",
        file_bytes=path.stat().st_size,
        characters=visible_length(text),
        kanji=len(kanji_chars),
        unique_kanji=len(set(kanji_chars)),
        kana=len(KANA_RE.findall(text)),
        sentences=len(sentences),
        average_sentence_length=statistics.fmean(sentence_lengths) if sentence_lengths else 0.0,
        paragraphs=parser.paragraphs,
        headings=parser.headings,
        ruby=parser.ruby,
        images=parser.images,
    )


def percentile(values: list[int], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def describe(label: str, values: list[int]) -> None:
    print(
        f"{label:<19} min={min(values):>8,}  p25={percentile(values, .25):>8,.0f}  "
        f"median={statistics.median(values):>8,.0f}  p75={percentile(values, .75):>8,.0f}  "
        f"max={max(values):>8,}  mean={statistics.fmean(values):>8,.0f}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("reduced_corpus"))
    parser.add_argument("--metadata", type=Path, default=Path("reduced_aozora.csv"))
    parser.add_argument("--min-characters", type=int, default=1_000, help="Flag works below this visible-character count")
    parser.add_argument("--outlier-limit", type=int, default=20, help="Maximum flagged works to print per category")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata = metadata_by_id(args.metadata)
    files = sorted(args.corpus.glob("*.html"))
    if not files:
        raise SystemExit(f"No HTML files found in {args.corpus}")
    stats = [analyze_work(path, metadata.get(path.stem, {})) for path in files]

    print("Corpus overview")
    print("===============")
    print(f"Works:                 {len(stats)}")
    print(f"Authors:               {len(set(item.author for item in stats))}")
    print(f"Total visible chars:   {sum(item.characters for item in stats):,}")
    print(f"Total file bytes:      {sum(item.file_bytes for item in stats):,}")
    print(f"Files with headings:   {sum(item.headings > 0 for item in stats)}")
    print(f"Files with ruby:       {sum(item.ruby > 0 for item in stats)}")
    print(f"Files with images:     {sum(item.images > 0 for item in stats)}")
    print("Works by author:")
    for author, count in sorted(Counter(item.author for item in stats).items()):
        print(f"  {author}: {count}")

    print("\nDistributions")
    print("=============")
    describe("Visible characters", [item.characters for item in stats])
    describe("File bytes", [item.file_bytes for item in stats])
    describe("Sentences", [item.sentences for item in stats])
    describe("Unique kanji", [item.unique_kanji for item in stats])

    short = sorted((item for item in stats if item.characters < args.min_characters), key=lambda item: item.characters)
    no_sentences = [item for item in stats if item.sentences == 0]
    replacement = [path.name for path in files if "�" in read_shift_jis(path)]
    print("\nPotential outliers")
    print("==================")
    print(f"Below {args.min_characters:,} visible characters: {len(short)}")
    for item in short[: args.outlier_limit]:
        print(f"  {item.work_id}  {item.characters:>7,}  {item.author} — {item.title}")
    print(f"No detected sentences: {len(no_sentences)}")
    print(f"Decode replacements:   {len(replacement)}")
    for name in replacement[: args.outlier_limit]:
        print(f"  {name}")

    print("\nNote: Japanese word counts require a morphological tokenizer. Character,")
    print("sentence, kanji, and layout measures here are dependency-free QC signals.")


if __name__ == "__main__":
    main()
