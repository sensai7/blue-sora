"""Render canonical Aozora content for accessible static work pages."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from markupsafe import Markup


SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


@dataclass(frozen=True)
class RenderedSection:
    html: Markup
    toc: list[dict[str, Any]]


def safe_id(value: str, fallback: str) -> str:
    cleaned = SAFE_ID_RE.sub("-", value.strip()).strip("-")
    return cleaned or fallback


def render_inlines(nodes: list[dict[str, Any]], asset_urls: dict[str, str]) -> str:
    output: list[str] = []
    for node in nodes:
        node_type = node["type"]
        if node_type == "text":
            output.append(html.escape(node["text"]))
        elif node_type == "line_break":
            output.append("<br>")
        elif node_type == "ruby":
            output.append(
                f"<ruby>{render_inlines(node['base'], asset_urls)}"
                f"<rt>{html.escape(node['reading'])}</rt></ruby>"
            )
        elif node_type in {"illustration", "gaiji"}:
            label = node.get("alt") or ("Illustration" if node_type == "illustration" else "Gaiji character")
            url = asset_urls.get(node.get("asset_id", ""))
            if url:
                output.append(
                    f'<img class="{node_type}" src="{html.escape(url, quote=True)}" '
                    f'alt="{html.escape(label, quote=True)}" loading="lazy" decoding="async">'
                )
            else:
                output.append(
                    f'<span class="missing-image" role="img" aria-label="{html.escape(label, quote=True)}">'
                    f'[{html.escape(label)} unavailable]</span>'
                )
        elif node_type == "emphasis":
            style = html.escape(node.get("style", "emphasis"), quote=True)
            output.append(f'<em class="{style}">{render_inlines(node.get("children", []), asset_urls)}</em>')
        elif node_type in {"warichu", "note", "styled"}:
            classes = node.get("styles") or [node_type]
            role = ' role="note"' if node_type == "note" else ""
            output.append(
                f'<span class="{html.escape(" ".join(classes), quote=True)}"{role}>'
                f'{render_inlines(node.get("children", []), asset_urls)}</span>'
            )
        elif node_type == "anchor":
            identifier = node.get("id")
            id_attribute = f' id="{html.escape(safe_id(identifier, "source-anchor"), quote=True)}"' if identifier else ""
            output.append(
                f'<span{id_attribute}>'
                f'{render_inlines(node.get("children", []), asset_urls)}</span>'
            )
        elif node_type in {"small", "subscript", "superscript"}:
            tag = {"small": "small", "subscript": "sub", "superscript": "sup"}[node_type]
            style = f' class="{html.escape(node["style"], quote=True)}"' if node.get("style") else ""
            output.append(f"<{tag}{style}>{render_inlines(node.get('children', []), asset_urls)}</{tag}>")
        elif node_type == "source_markup":
            classes = html.escape(" ".join(node.get("classes", [])), quote=True)
            output.append(
                f'<span class="source-markup {classes}">'
                f'{render_inlines(node.get("children", []), asset_urls)}</span>'
            )
    return "".join(output)


def inline_text(nodes: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        if node["type"] == "text":
            parts.append(node["text"])
        elif node["type"] == "ruby":
            parts.append(inline_text(node.get("base", [])))
        else:
            parts.append(inline_text(node.get("children", [])))
    return "".join(parts).strip()


def render_blocks(
    blocks: list[dict[str, Any]],
    asset_urls: dict[str, str],
    *,
    collect_toc: bool = False,
) -> RenderedSection:
    lines: list[str] = []
    toc: list[dict[str, Any]] = []
    heading_number = 0
    for block in blocks:
        block_type = block["type"]
        if block_type == "heading":
            heading_number += 1
            level = min(4, max(2, int(block.get("level", 2))))
            label = inline_text(block.get("inlines", [])) or f"Section {heading_number}"
            identifier = f"section-{heading_number}"
            lines.append(
                f'<h{level} id="{identifier}">{render_inlines(block.get("inlines", []), asset_urls)}'
                f'<a class="heading-anchor" href="#{identifier}" aria-label="Link to {html.escape(label, quote=True)}">#</a>'
                f"</h{level}>"
            )
            if collect_toc:
                toc.append({"id": identifier, "level": level, "label": label})
        elif block_type == "paragraph":
            lines.append(f'<p>{render_inlines(block.get("inlines", []), asset_urls)}</p>')
        elif block_type == "separator":
            lines.append('<hr aria-hidden="true">')
        elif block_type == "list":
            tag = "ol" if block.get("ordered") else "ul"
            items = "".join(
                f"<li>{render_blocks(item, asset_urls).html}</li>" for item in block.get("items", [])
            )
            lines.append(f"<{tag}>{items}</{tag}>")
            supplemental = render_blocks(block.get("supplemental", []), asset_urls)
            if supplemental.html:
                lines.append(str(supplemental.html))
        elif block_type == "table":
            rows = "".join(
                "<tr>" + "".join(
                    f"<td>{render_blocks(cell, asset_urls).html}</td>" for cell in row
                ) + "</tr>" for row in block.get("rows", [])
            )
            lines.append(f'<div class="reader-table-wrap"><table>{rows}</table></div>')
        elif block_type == "styled_block":
            classes = html.escape(" ".join(block.get("styles", [])), quote=True)
            child = render_blocks(block.get("blocks", []), asset_urls)
            lines.append(f'<div class="{classes}">{child.html}</div>')
    return RenderedSection(Markup("\n".join(lines)), toc)


def export_state(output_dir: Path, slug: str, export_format: str, url_prefix: str = "") -> dict[str, str]:
    extension = export_format.lower()
    label = export_format.upper()
    relative = Path("downloads") / f"{slug}.{extension}"
    artifact = output_dir / relative
    error_marker = output_dir / "downloads" / f"{slug}.{extension}.error.txt"
    if artifact.is_file():
        return {
            "format": label,
            "status": "available",
            "url": f"{url_prefix}{relative.as_posix()}",
            "detail": f"{label} ready",
        }
    if error_marker.is_file():
        return {
            "format": label,
            "status": "error",
            "url": "",
            "detail": f"{label} generation failed",
        }
    milestone = "M8" if extension == "epub" else "M9"
    return {
        "format": label,
        "status": "unavailable",
        "url": "",
        "detail": f"Available after {milestone}",
    }
