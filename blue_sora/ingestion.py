"""Convert Aozora XHTML into a deterministic, source-independent model."""

from __future__ import annotations

import hashlib
import html as html_module
import mimetypes
import re
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urljoin, urlparse


PARSER_VERSION = "0.1.0"
SECTION_CLASSES = {
    "main_text": "body",
    "bibliographical_information": "bibliography",
    "notation_notes": "notation_notes",
}
HEADING_LEVELS = {
    "o-midashi": 2,
    "naka-midashi": 3,
    "mado-naka-midashi": 3,
    "dogyo-naka-midashi": 3,
    "ko-midashi": 4,
    "dogyo-ko-midashi": 4,
}
KNOWN_INLINE_TAGS = {"a", "b", "em", "i", "img", "rb", "rp", "rt", "ruby", "span", "strong", "br"}
KNOWN_INLINE_CLASSES = {
    "author", "burasage", "chitsuki_0", "futoji", "gaiji", "illustration",
    "keigakomi", "midashi_anchor", "notes", "sesame_dot", "title", "warichu",
}
BLOCK_TAGS = {"div", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "p"}
STYLE_CLASSES = {"caption", "dai1", "shatai", "sho1", "yokogumi"}


@dataclass
class Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return {item.lower() for item in self.attrs.get("class", "").split()}


class TreeParser(HTMLParser):
    """Small forgiving tree builder suitable for the fixed Aozora XHTML shell."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self.stack[-1].children.append(element)
        if element.tag not in self.VOID_TAGS:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


class AssetRegistry:
    def __init__(self, source_url: str) -> None:
        self.source_url = source_url
        self.assets: dict[str, dict[str, Any]] = {}

    def add(self, source: str, kind: str) -> str:
        original_url = urljoin(self.source_url, source)
        asset_id = hashlib.sha256(original_url.encode("utf-8")).hexdigest()[:16]
        suffix = PurePosixPath(unquote(urlparse(original_url).path)).suffix.lower()
        if not suffix or len(suffix) > 8:
            suffix = mimetypes.guess_extension(mimetypes.guess_type(original_url)[0] or "") or ".bin"
        self.assets.setdefault(
            asset_id,
            {
                "id": asset_id,
                "kind": kind,
                "original_url": original_url,
                "local_path": f"assets/{asset_id}{suffix}",
                "status": "pending",
                "mime_type": None,
                "byte_size": None,
                "sha256": None,
                "diagnostic": None,
            },
        )
        return asset_id


def walk(elements: Iterable[Element | str]) -> Iterable[Element]:
    for child in elements:
        if isinstance(child, Element):
            yield child
            yield from walk(child.children)


def find_section(root: Element, class_name: str) -> Element | None:
    return next((element for element in walk(root.children) if class_name in element.classes), None)


def plain_text(nodes: Iterable[Element | str], *, ruby_reading: bool = False) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        elif node.tag == "rp":
            continue
        elif node.tag == "rt" and not ruby_reading:
            continue
        else:
            parts.append(plain_text(node.children, ruby_reading=ruby_reading))
    return "".join(parts)


class Canonicalizer:
    def __init__(self, source_url: str) -> None:
        self.assets = AssetRegistry(source_url)
        self.warnings: list[dict[str, Any]] = []

    def warn(self, code: str, **details: Any) -> None:
        warning = {"code": code, **details}
        if warning not in self.warnings:
            self.warnings.append(warning)

    def inline(self, node: Element | str) -> list[dict[str, Any]]:
        if isinstance(node, str):
            return [{"type": "text", "text": node}] if node else []
        if node.tag == "br":
            return [{"type": "line_break"}]
        if node.tag == "rp":
            return []
        if node.tag == "ruby":
            bases = [child for child in node.children if not isinstance(child, Element) or child.tag not in {"rt", "rp"}]
            readings = [child for child in node.children if isinstance(child, Element) and child.tag == "rt"]
            return [{
                "type": "ruby",
                "base": self.inlines(bases),
                "reading": "".join(plain_text(item.children, ruby_reading=True) for item in readings),
            }]
        if node.tag == "img":
            source = node.attrs.get("src", "")
            if not source:
                self.warn("image_without_source", tag="img")
                return [{"type": "image", "asset_id": None, "alt": node.attrs.get("alt", "")}]
            kind = "gaiji" if "gaiji" in node.classes or "gaiji" in node.attrs else "illustration"
            return [{
                "type": kind,
                "asset_id": self.assets.add(source, kind),
                "alt": node.attrs.get("alt", ""),
            }]

        children = self.inlines(node.children)
        classes = node.classes
        if "warichu" in classes:
            return [{"type": "warichu", "children": children}]
        if "notes" in classes:
            return [{"type": "note", "children": children}]
        if node.tag in {"strong", "b", "em", "i"} or classes & {"sesame_dot", "futoji"}:
            style = "sesame_dot" if "sesame_dot" in classes else "strong"
            return [{"type": "emphasis", "style": style, "children": children}]
        if node.tag == "a":
            return [{"type": "anchor", "id": node.attrs.get("id") or node.attrs.get("name"), "children": children}]
        if node.tag in {"small", "sub", "sup"}:
            return [{
                "type": {"small": "small", "sub": "subscript", "sup": "superscript"}[node.tag],
                "style": next(iter(sorted(classes)), None),
                "children": children,
            }]
        if classes & STYLE_CLASSES:
            return [{"type": "styled", "styles": sorted(classes & STYLE_CLASSES), "children": children}]
        unknown_classes = sorted(
            item for item in classes
            if item not in KNOWN_INLINE_CLASSES and not item.startswith(("jisage_", "chitsuki_"))
        )
        if node.tag not in KNOWN_INLINE_TAGS or unknown_classes:
            self.warn("unrecognized_markup", tag=node.tag, classes=unknown_classes)
            return [{"type": "source_markup", "tag": node.tag, "classes": sorted(classes), "children": children}]
        return children

    def inlines(self, nodes: Iterable[Element | str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for node in nodes:
            result.extend(self.inline(node))
        return result

    @staticmethod
    def trim_layout_whitespace(inlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if inlines and inlines[0].get("type") == "text":
            inlines[0]["text"] = inlines[0].get("text", "").lstrip(" \t\r\n")
        if inlines and inlines[-1].get("type") == "text":
            inlines[-1]["text"] = inlines[-1].get("text", "").rstrip(" \t\r\n")
        while inlines and inlines[0].get("type") == "text" and not inlines[0].get("text"):
            inlines.pop(0)
        while inlines and inlines[-1].get("type") == "text" and not inlines[-1].get("text"):
            inlines.pop()
        return inlines

    def heading_level(self, element: Element) -> int:
        for class_name, level in HEADING_LEVELS.items():
            if class_name in element.classes:
                return level
        if element.tag.startswith("h") and element.tag[1:].isdigit():
            return min(4, max(2, int(element.tag[1:])))
        return 3

    def blocks(self, section: Element | None) -> list[dict[str, Any]]:
        if section is None:
            return []
        blocks: list[dict[str, Any]] = []
        loose: list[Element | str] = []

        def flush() -> None:
            if not loose:
                return
            inlines = self.trim_layout_whitespace(self.inlines(loose))
            loose.clear()
            if any(item.get("type") != "text" or item.get("text", "").strip() for item in inlines):
                blocks.append({"type": "paragraph", "inlines": inlines})

        for child in section.children:
            if isinstance(child, str):
                loose.append(child)
                continue
            heading_class = child.classes & set(HEADING_LEVELS)
            if child.tag in {"h1", "h2", "h3", "h4", "h5", "h6"} or heading_class:
                flush()
                blocks.append({"type": "heading", "level": self.heading_level(child), "inlines": self.trim_layout_whitespace(self.inlines(child.children))})
            elif child.tag == "hr":
                flush()
                blocks.append({"type": "separator"})
            elif child.tag == "p":
                flush()
                blocks.append({"type": "paragraph", "inlines": self.trim_layout_whitespace(self.inlines(child.children))})
            elif child.tag in {"ul", "ol"}:
                flush()
                items = [
                    self.blocks(item)
                    for item in child.children
                    if isinstance(item, Element) and item.tag == "li"
                ]
                supplemental_nodes = [
                    item for item in child.children
                    if not (isinstance(item, Element) and item.tag in {"li", "br"})
                    and not (isinstance(item, str) and not item.strip())
                ]
                supplemental = self.blocks(Element("div", children=supplemental_nodes))
                blocks.append({
                    "type": "list",
                    "ordered": child.tag == "ol",
                    "items": items,
                    "supplemental": supplemental,
                })
            elif child.tag == "table":
                flush()
                rows: list[list[list[dict[str, Any]]]] = []
                for row in (item for item in walk(child.children) if item.tag == "tr"):
                    cells = [
                        self.blocks(cell)
                        for cell in row.children
                        if isinstance(cell, Element) and cell.tag in {"td", "th"}
                    ]
                    rows.append(cells)
                blocks.append({"type": "table", "style": sorted(child.classes), "rows": rows})
            elif child.tag == "br":
                flush()
            elif child.tag == "div":
                flush()
                nested = self.blocks(child)
                if nested:
                    styles = sorted(child.classes)
                    if styles:
                        blocks.append({"type": "styled_block", "styles": styles, "blocks": nested})
                    else:
                        blocks.extend(nested)
            else:
                loose.append(child)
        flush()
        return blocks


def canonical_text(value: Any) -> str:
    """Return the source-visible text represented by canonical nodes."""
    if isinstance(value, list):
        return "".join(canonical_text(item) for item in value)
    if not isinstance(value, dict):
        return ""
    node_type = value.get("type")
    if node_type == "text":
        return value.get("text", "")
    if node_type == "ruby":
        return canonical_text(value.get("base", []))
    if node_type in {"paragraph", "heading"}:
        return canonical_text(value.get("inlines", []))
    if node_type in {"emphasis", "warichu", "note", "anchor", "small", "subscript", "superscript", "styled", "source_markup"}:
        return canonical_text(value.get("children", []))
    if node_type == "list":
        return canonical_text(value.get("items", [])) + canonical_text(value.get("supplemental", []))
    if node_type == "table":
        return canonical_text(value.get("rows", []))
    if node_type == "styled_block":
        return canonical_text(value.get("blocks", []))
    return ""


def normalized_semantic_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def ingest_work(
    source_bytes: bytes,
    metadata: dict[str, str],
    *,
    source_filename: str,
    source_url: str,
) -> dict[str, Any]:
    html = source_bytes.decode("cp932")
    parser = TreeParser()
    parser.feed(html)
    canonicalizer = Canonicalizer(source_url)
    sections: dict[str, list[dict[str, Any]]] = {}
    section_hashes: dict[str, str] = {}
    for source_class, canonical_name in SECTION_CLASSES.items():
        source_section = find_section(parser.root, source_class)
        sections[canonical_name] = canonicalizer.blocks(source_section)
        if source_section is None:
            canonicalizer.warn("missing_section", section=canonical_name, source_class=source_class)
            continue
        source_text = plain_text(source_section.children)
        output_text = canonical_text(sections[canonical_name])
        section_hashes[canonical_name] = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        if normalized_semantic_text(source_text) != normalized_semantic_text(output_text):
            canonicalizer.warn(
                "text_loss",
                section=canonical_name,
                source_characters=len(source_text),
                canonical_characters=len(output_text),
            )

    return {
        "schema_version": 1,
        "metadata": metadata,
        "content": sections,
        "assets": sorted(canonicalizer.assets.assets.values(), key=lambda asset: asset["id"]),
        "provenance": {
            "source_filename": source_filename,
            "source_url": source_url,
            "source_encoding": "cp932",
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "parser_version": PARSER_VERSION,
            "section_text_sha256": section_hashes,
        },
        "warnings": sorted(canonicalizer.warnings, key=lambda item: repr(sorted(item.items()))),
    }


def render_inlines(nodes: list[dict[str, Any]], assets: dict[str, dict[str, Any]]) -> str:
    output: list[str] = []
    for node in nodes:
        node_type = node["type"]
        if node_type == "text":
            output.append(html_module.escape(node["text"]))
        elif node_type == "line_break":
            output.append("<br>")
        elif node_type == "ruby":
            output.append(f"<ruby>{render_inlines(node['base'], assets)}<rt>{html_module.escape(node['reading'])}</rt></ruby>")
        elif node_type in {"illustration", "gaiji"}:
            asset = assets.get(node.get("asset_id"), {})
            output.append(
                f'<img class="{node_type}" src="{html_module.escape(asset.get("local_path", ""), quote=True)}" '
                f'alt="{html_module.escape(node.get("alt", ""), quote=True)}">'
            )
        elif node_type == "emphasis":
            output.append(f'<em class="{html_module.escape(node["style"], quote=True)}">{render_inlines(node["children"], assets)}</em>')
        elif node_type in {"warichu", "note", "styled"}:
            classes = node.get("styles", [node_type])
            output.append(f'<span class="{html_module.escape(" ".join(classes), quote=True)}">{render_inlines(node["children"], assets)}</span>')
        elif node_type == "anchor":
            identifier = html_module.escape(node.get("id") or "", quote=True)
            output.append(f'<span id="{identifier}">{render_inlines(node["children"], assets)}</span>')
        elif node_type in {"small", "subscript", "superscript"}:
            tag = {"small": "small", "subscript": "sub", "superscript": "sup"}[node_type]
            style = f' class="{html_module.escape(node["style"], quote=True)}"' if node.get("style") else ""
            output.append(f"<{tag}{style}>{render_inlines(node['children'], assets)}</{tag}>")
        elif node_type == "source_markup":
            classes = html_module.escape(" ".join(node.get("classes", [])), quote=True)
            output.append(f'<span class="source-markup {classes}">{render_inlines(node["children"], assets)}</span>')
    return "".join(output)


def render_blocks(blocks: list[dict[str, Any]], assets: list[dict[str, Any]]) -> str:
    asset_map = {asset["id"]: asset for asset in assets}
    lines: list[str] = []
    for block in blocks:
        block_type = block["type"]
        if block_type == "heading":
            level = block["level"]
            lines.append(f"<h{level}>{render_inlines(block['inlines'], asset_map)}</h{level}>")
        elif block_type == "paragraph":
            lines.append(f"<p>{render_inlines(block['inlines'], asset_map)}</p>")
        elif block_type == "separator":
            lines.append("<hr>")
        elif block_type == "list":
            tag = "ol" if block["ordered"] else "ul"
            items = "".join(f"<li>{render_blocks(item, assets)}</li>" for item in block["items"])
            supplemental = render_blocks(block.get("supplemental", []), assets)
            lines.append(f"<{tag}>{items}</{tag}>" + (f"\n{supplemental}" if supplemental else ""))
        elif block_type == "table":
            rows = "".join(
                "<tr>" + "".join(f"<td>{render_blocks(cell, assets)}</td>" for cell in row) + "</tr>"
                for row in block["rows"]
            )
            lines.append(f"<table>{rows}</table>")
        elif block_type == "styled_block":
            classes = html_module.escape(" ".join(block["styles"]), quote=True)
            lines.append(f'<div class="{classes}">{render_blocks(block["blocks"], assets)}</div>')
    return "\n".join(lines)


Fetcher = Callable[[str], tuple[bytes, str | None]]


def network_fetch(url: str) -> tuple[bytes, str | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "BlueSora/0.1 (+offline corpus builder)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), response.headers.get_content_type()


def download_assets(document: dict[str, Any], output_dir: Path, fetcher: Fetcher = network_fetch) -> None:
    for asset in document["assets"]:
        destination = output_dir / asset["local_path"]
        try:
            if destination.is_file():
                payload = destination.read_bytes()
                mime_type = mimetypes.guess_type(destination.name)[0]
            else:
                payload, mime_type = fetcher(asset["original_url"])
            if mime_type and not mime_type.startswith("image/"):
                raise ValueError(f"unsupported MIME type: {mime_type}")
            if not destination.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
            asset.update({
                "status": "stored",
                "mime_type": mime_type or mimetypes.guess_type(destination.name)[0],
                "byte_size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "diagnostic": None,
            })
        except Exception as error:  # Diagnostics are part of the canonical result.
            asset.update({"status": "error", "diagnostic": f"{type(error).__name__}: {error}"})
