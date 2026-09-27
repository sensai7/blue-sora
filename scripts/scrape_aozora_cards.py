"""Download Aozora Bunko XHTML files linked from card pages.

Examples:
    # Verify one card page first.
    python scripts/scrape_aozora_cards.py --url https://www.aozora.gr.jp/cards/001779/card57105.html

    # Download every card listed one per line in aozora_card_links.txt.
    python scripts/scrape_aozora_cards.py --input aozora_card_links.txt
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
from time import sleep
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "blue-sora-aozora-scraper/1.0"


class CardPageParser(HTMLParser):
    """Find XHTML work-file links from a card page's download area."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.xhtml_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._anchor_href = dict(attrs).get("href")
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            label = "".join(self._anchor_text).replace(" ", "").replace("\n", "")
            if "XHTML" in label and "files/" in self._anchor_href:
                self.xhtml_links.append(self._anchor_href)
            self._anchor_href = None
            self._anchor_text = []


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def decode_card_html(card_html: bytes) -> str:
    """Decode Aozora card pages, which are commonly Shift_JIS/CP932."""
    match = re.search(
        rb"<meta[^>]+charset=[\"']?([A-Za-z0-9_-]+)", card_html[:4096], re.IGNORECASE
    )
    encodings = [match.group(1).decode("ascii")] if match else []
    encodings.extend(["utf-8", "cp932"])
    for encoding in dict.fromkeys(encodings):
        try:
            return card_html.decode(encoding)
        except UnicodeDecodeError:
            pass
    return card_html.decode("cp932", errors="replace")


def xhtml_urls(card_url: str, card_html: bytes) -> list[str]:
    parser = CardPageParser()
    parser.feed(decode_card_html(card_html))
    parser.close()
    return list(dict.fromkeys(urljoin(card_url, href) for href in parser.xhtml_links))


def destination_for(url: str, output: Path) -> Path:
    """Keep source filenames while preventing same-name files from overwriting."""
    parsed = urlparse(url)
    author_id = next((part for part in parsed.path.split("/") if part.isdigit() and len(part) == 6), "unknown")
    filename = Path(parsed.path).name
    return output / f"{author_id}_{filename}"


def card_urls_from_file(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.startswith("#")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", action="append", help="A card page URL; may be passed more than once.")
    source.add_argument("--input", type=Path, help="Text file containing one card page URL per line.")
    parser.add_argument("--output", type=Path, default=Path("scraped"), help="Destination directory (default: scraped).")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between card-page requests (default: 1).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    card_urls = args.url or card_urls_from_file(args.input)
    args.output.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    for index, card_url in enumerate(card_urls):
        if index:
            sleep(args.delay)
        try:
            targets = xhtml_urls(card_url, fetch(card_url))
            if not targets:
                print(f"SKIP {card_url}: no XHTMLファイル link found")
                continue
            for target in targets:
                destination = destination_for(target, args.output)
                destination.write_bytes(fetch(target))
                downloaded += 1
                print(f"SAVED {destination} <- {target}")
        except OSError as error:
            print(f"ERROR {card_url}: {error}")

    print(f"Downloaded {downloaded} XHTML file(s) to {args.output}")


if __name__ == "__main__":
    main()
