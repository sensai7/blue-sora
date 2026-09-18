"""Inspect structural variation in Aozora HTML files."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([^\s\"'/>;]+)", re.IGNORECASE)


class StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: Counter[str] = Counter()
        self.classes: Counter[str] = Counter()
        self.heading_tags: Counter[str] = Counter()
        self.heading_classes: Counter[str] = Counter()
        self.has_main_text = False
        self.meta_creator = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        self.tags[tag] += 1
        self.classes.update(classes)
        if "main_text" in classes:
            self.has_main_text = True
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_tags[tag] += 1
        self.heading_classes.update(c for c in classes if "midashi" in c)
        if tag == "meta" and (attributes.get("name") or "").lower() == "dc.creator":
            self.meta_creator = attributes.get("content") or ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("reduced_corpus"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = sorted(args.corpus.glob("*.html"))
    if not files:
        raise SystemExit(f"No HTML files found in {args.corpus}")

    charsets: Counter[str] = Counter()
    doctypes: Counter[str] = Counter()
    files_with_main = 0
    files_with_creator = 0
    aggregate_tags: Counter[str] = Counter()
    aggregate_classes: Counter[str] = Counter()
    heading_tags: Counter[str] = Counter()
    heading_classes: Counter[str] = Counter()

    for path in files:
        html = path.read_text(encoding="cp932", errors="replace")
        match = CHARSET_RE.search(html[:2_000])
        charsets[(match.group(1) if match else "undeclared").lower()] += 1
        prefix = html[:1_000].lower()
        if "xhtml 1.1" in prefix:
            doctypes["XHTML 1.1"] += 1
        elif "html 4.01" in prefix:
            doctypes["HTML 4.01"] += 1
        elif "<!doctype" in prefix:
            doctypes["Other doctype"] += 1
        else:
            doctypes["No doctype"] += 1
        parser = StructureParser()
        parser.feed(html)
        files_with_main += parser.has_main_text
        files_with_creator += bool(parser.meta_creator)
        aggregate_tags.update(parser.tags)
        aggregate_classes.update(parser.classes)
        heading_tags.update(parser.heading_tags)
        heading_classes.update(parser.heading_classes)

    print(f"Files inspected: {len(files)}")
    print(f"With div.main_text: {files_with_main}")
    print(f"With DC.Creator: {files_with_creator}")
    print("Declared charsets:", dict(charsets))
    print("Document types:", dict(doctypes))
    print("Heading tags:", dict(heading_tags))
    print("Heading classes:", dict(heading_classes))
    print("Most common tags:", aggregate_tags.most_common(20))
    print("Most common classes:", aggregate_classes.most_common(30))


if __name__ == "__main__":
    main()
