"""Basic HTML and accessibility validation for generated pages."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class PageAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.doctype = False
        self.html_lang = ""
        self.in_title = False
        self.title = ""
        self.viewport = False
        self.main_ids: list[str] = []
        self.h1_count = 0
        self.errors: list[str] = []
        self.asset_urls: list[str] = []
        self.image_urls: list[str] = []
        self.cover_placeholders = 0
        self.ruby_depth = 0
        self.ruby_has_rt: list[bool] = []

    def handle_decl(self, decl: str) -> None:
        if decl.lower() == "doctype html":
            self.doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "html":
            self.html_lang = attributes.get("lang") or ""
        elif tag == "title":
            self.in_title = True
        elif tag == "meta" and attributes.get("name") == "viewport":
            self.viewport = bool(attributes.get("content"))
        elif tag == "main":
            self.main_ids.append(attributes.get("id") or "")
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "img":
            if "alt" not in attributes:
                self.errors.append("image is missing alt text")
            if attributes.get("src"):
                self.image_urls.append(attributes["src"])
        elif tag == "a" and not attributes.get("href"):
            self.errors.append("link is missing href")
        elif tag == "button" and not attributes.get("aria-label"):
            self.errors.append("button is missing an accessible label")
        elif tag in {"link", "script"}:
            url = attributes.get("href") if tag == "link" else attributes.get("src")
            if url:
                self.asset_urls.append(url)
        if attributes.get("data-library-url"):
            self.asset_urls.append(attributes["data-library-url"])
        if "book-cover--empty" in classes:
            self.cover_placeholders += 1
            if attributes.get("role") != "img" or not attributes.get("aria-label"):
                self.errors.append("empty cover lacks an accessible image label")
        if tag == "ruby":
            self.ruby_depth += 1
            self.ruby_has_rt.append(False)
        elif tag == "rt" and self.ruby_depth:
            self.ruby_has_rt[-1] = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "ruby" and self.ruby_depth:
            if not self.ruby_has_rt.pop():
                self.errors.append("ruby element is missing rt")
            self.ruby_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data

    def results(self) -> list[str]:
        errors = list(self.errors)
        if not self.doctype:
            errors.append("missing HTML5 doctype")
        if not self.html_lang:
            errors.append("html element is missing lang")
        if not self.title.strip():
            errors.append("page title is empty")
        if not self.viewport:
            errors.append("viewport metadata is missing")
        if len(self.main_ids) != 1:
            errors.append("page must contain exactly one main landmark")
        if self.h1_count != 1:
            errors.append("page must contain exactly one h1")
        return errors


def audit_html(path: Path) -> PageAudit:
    parser = PageAudit()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
    return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)
