"""Deterministic EPUB 3 generation from Blue Sora catalog artifacts."""

from __future__ import annotations

import hashlib
import html
import io
import json
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from .reader import export_filename


EPUB_GENERATOR_VERSION = "blue-sora-epub-v1"
EPUB_NAMESPACE = "http://www.idpf.org/2007/ops"
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
OPF_NAMESPACE = "http://www.idpf.org/2007/opf"
CONTAINER_NAMESPACE = "urn:oasis:names:tc:opendocument:xmlns:container"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


EPUB_CSS = """@charset "UTF-8";
html { writing-mode: vertical-rl; -epub-writing-mode: vertical-rl; }
body { font-family: serif; line-height: 1.9; margin: 6%; }
body.cover, body.navigation { writing-mode: horizontal-tb; -epub-writing-mode: horizontal-tb; }
h1, h2, h3, h4 { font-weight: 600; }
p { margin: 0 0 1em; }
ruby { ruby-position: over; }
rt { font-size: 0.5em; }
img { max-width: 90%; max-height: 90%; object-fit: contain; }
.gaiji { width: 1em; height: 1em; vertical-align: text-bottom; }
.cover-image { display: block; margin: auto; max-width: 100%; max-height: 100%; }
.warichu, .note { font-size: 0.75em; }
.sesame_dot { text-emphasis-style: sesame; -webkit-text-emphasis-style: sesame; }
.source-attribution { font-size: 0.85em; }
table { border-collapse: collapse; }
td { border: 1px solid currentColor; padding: 0.3em; }
"""


@dataclass(frozen=True)
class Chapter:
    filename: str
    title: str
    blocks: list[dict[str, Any]]


def xml_escape(value: Any, *, quote: bool = False) -> str:
    return html.escape(str(value or ""), quote=quote)


def safe_id(value: str, fallback: str) -> str:
    cleaned = SAFE_ID_RE.sub("-", value.strip()).strip("-")
    return cleaned or fallback


def inline_text(nodes: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "text":
            parts.append(node.get("text", ""))
        elif node_type == "ruby":
            parts.append(inline_text(node.get("base", [])))
        else:
            parts.append(inline_text(node.get("children", [])))
    return "".join(parts).strip()


def render_inlines(nodes: Iterable[dict[str, Any]], asset_hrefs: dict[str, str]) -> str:
    output: list[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "text":
            output.append(xml_escape(node.get("text", "")))
        elif node_type == "line_break":
            output.append("<br />")
        elif node_type == "ruby":
            output.append(
                f"<ruby>{render_inlines(node.get('base', []), asset_hrefs)}"
                f"<rt>{xml_escape(node.get('reading', ''))}</rt></ruby>"
            )
        elif node_type in {"illustration", "gaiji"}:
            label = node.get("alt") or ("Illustration" if node_type == "illustration" else "Gaiji character")
            href = asset_hrefs.get(node.get("asset_id", ""))
            if href:
                output.append(
                    f'<img class="{node_type}" src="{xml_escape(href, quote=True)}" '
                    f'alt="{xml_escape(label, quote=True)}" />'
                )
            else:
                output.append(f'<span class="missing-image">[{xml_escape(label)} unavailable]</span>')
        elif node_type == "emphasis":
            style = xml_escape(node.get("style", "emphasis"), quote=True)
            output.append(f'<em class="{style}">{render_inlines(node.get("children", []), asset_hrefs)}</em>')
        elif node_type in {"warichu", "note", "styled"}:
            classes = node.get("styles") or [node_type]
            output.append(
                f'<span class="{xml_escape(" ".join(classes), quote=True)}">'
                f'{render_inlines(node.get("children", []), asset_hrefs)}</span>'
            )
        elif node_type == "anchor":
            identifier = node.get("id")
            identifier_attr = f' id="{xml_escape(safe_id(identifier, "source-anchor"), quote=True)}"' if identifier else ""
            output.append(f'<span{identifier_attr}>{render_inlines(node.get("children", []), asset_hrefs)}</span>')
        elif node_type in {"small", "subscript", "superscript"}:
            tag = {"small": "small", "subscript": "sub", "superscript": "sup"}[node_type]
            output.append(f'<{tag}>{render_inlines(node.get("children", []), asset_hrefs)}</{tag}>')
        elif node_type == "source_markup":
            classes = "source-markup " + " ".join(node.get("classes", []))
            output.append(
                f'<span class="{xml_escape(classes, quote=True)}">'
                f'{render_inlines(node.get("children", []), asset_hrefs)}</span>'
            )
    return "".join(output)


def render_blocks(blocks: Iterable[dict[str, Any]], asset_hrefs: dict[str, str]) -> str:
    lines: list[str] = []
    heading_number = 0
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading":
            heading_number += 1
            level = min(4, max(2, int(block.get("level", 2))))
            lines.append(
                f'<h{level} id="heading-{heading_number}">'
                f'{render_inlines(block.get("inlines", []), asset_hrefs)}</h{level}>'
            )
        elif block_type == "paragraph":
            lines.append(f'<p>{render_inlines(block.get("inlines", []), asset_hrefs)}</p>')
        elif block_type == "separator":
            lines.append("<hr />")
        elif block_type == "list":
            tag = "ol" if block.get("ordered") else "ul"
            items = "".join(
                f'<li>{render_blocks(item, asset_hrefs)}</li>' for item in block.get("items", [])
            )
            supplemental = render_blocks(block.get("supplemental", []), asset_hrefs)
            lines.append(f'<{tag}>{items}</{tag}>{supplemental}')
        elif block_type == "table":
            rows = "".join(
                "<tr>" + "".join(f'<td>{render_blocks(cell, asset_hrefs)}</td>' for cell in row) + "</tr>"
                for row in block.get("rows", [])
            )
            lines.append(f'<table>{rows}</table>')
        elif block_type == "styled_block":
            classes = xml_escape(" ".join(block.get("styles", [])), quote=True)
            lines.append(f'<div class="{classes}">{render_blocks(block.get("blocks", []), asset_hrefs)}</div>')
    return "\n".join(lines)


def split_chapters(blocks: list[dict[str, Any]]) -> list[Chapter]:
    chunks: list[tuple[str, list[dict[str, Any]]]] = []
    current: list[dict[str, Any]] = []
    current_title = "Text"
    for block in blocks:
        if block.get("type") == "heading" and current:
            chunks.append((current_title, current))
            current = []
        if block.get("type") == "heading":
            current_title = inline_text(block.get("inlines", [])) or f"Section {len(chunks) + 1}"
        current.append(block)
    if current:
        chunks.append((current_title, current))
    if not chunks:
        chunks.append(("Text", []))
    return [
        Chapter(filename=f"chapter-{index:03d}.xhtml", title=title, blocks=chapter_blocks)
        for index, (title, chapter_blocks) in enumerate(chunks, start=1)
    ]


def xhtml_document(title: str, body: str, *, body_class: str = "reading") -> bytes:
    document = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="{XHTML_NAMESPACE}" xmlns:epub="{EPUB_NAMESPACE}" xml:lang="ja" lang="ja">
<head><meta charset="utf-8" /><title>{xml_escape(title)}</title><link rel="stylesheet" type="text/css" href="styles/book.css" /></head>
<body class="{body_class}">{body}</body>
</html>
'''
    return document.encode("utf-8")


def cover_svg(title: str, authors: str) -> bytes:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1600" viewBox="0 0 1200 1600" role="img" aria-labelledby="title author">
<rect width="1200" height="1600" fill="#050505" />
<text id="title" x="600" y="650" text-anchor="middle" fill="#ffffff" font-family="serif" font-size="74">{xml_escape(title)}</text>
<text id="author" x="600" y="790" text-anchor="middle" fill="#d1d5db" font-family="serif" font-size="40">{xml_escape(authors)}</text>
<text x="600" y="1450" text-anchor="middle" fill="#93c5fd" font-family="sans-serif" font-size="30">Blue Sora · 青空文庫</text>
</svg>
'''.encode("utf-8")


def zip_info(name: str, *, stored: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def add_entry(archive: zipfile.ZipFile, name: str, payload: bytes, *, stored: bool = False) -> None:
    archive.writestr(zip_info(name, stored=stored), payload)


def modified_timestamp(work: dict[str, Any]) -> str:
    published = work.get("published_at") or "2000-01-01"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        published = "2000-01-01"
    return f"{published}T00:00:00Z"


def build_epub(work: dict[str, Any], authors: list[dict[str, Any]], catalog_root: Path) -> bytes:
    title = work["title"]["display"]
    author_names = [author["name"]["display"] for author in authors]
    author_label = "・".join(author_names)
    chapters = split_chapters(work["content"]["body"])
    stored_assets = [asset for asset in work["assets"] if asset.get("status") == "stored" and asset.get("build_path")]
    asset_hrefs = {asset["id"]: f'images/{asset["id"]}{PurePosixPath(asset["build_path"]).suffix.lower()}' for asset in stored_assets}

    entries: dict[str, bytes] = {}
    entries["META-INF/container.xml"] = f'''<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="{CONTAINER_NAMESPACE}"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml" /></rootfiles></container>
'''.encode("utf-8")
    entries["EPUB/styles/book.css"] = EPUB_CSS.encode("utf-8")
    entries["EPUB/images/cover.svg"] = cover_svg(title, author_label)
    entries["EPUB/cover.xhtml"] = xhtml_document(
        title,
        '<section epub:type="cover"><img class="cover-image" src="images/cover.svg" alt="Cover for '
        + xml_escape(title, quote=True) + '" /></section>',
        body_class="cover",
    )
    for chapter in chapters:
        entries[f"EPUB/{chapter.filename}"] = xhtml_document(
            chapter.title,
            render_blocks(chapter.blocks, asset_hrefs),
        )

    notes = work["content"].get("notation_notes", [])
    bibliography = work["content"].get("bibliography", [])
    entries["EPUB/colophon.xhtml"] = xhtml_document(
        "Source and edition notes",
        '<section epub:type="colophon"><h2>Source and edition notes</h2>'
        + render_blocks(notes, asset_hrefs)
        + render_blocks(bibliography, asset_hrefs)
        + '<p class="source-attribution">This edition was generated by Blue Sora from the canonical Aozora Bunko text. '
        + f'<a href="{xml_escape(work["source"].get("card_url"), quote=True)}">View the Aozora Bunko source card.</a></p></section>',
    )
    for asset in stored_assets:
        source = catalog_root.parent / asset["build_path"]
        if not source.is_file():
            raise FileNotFoundError(f"stored EPUB asset is missing: {source}")
        entries[f'EPUB/{asset_hrefs[asset["id"]]}'] = source.read_bytes()

    nav_items = "".join(
        f'<li><a href="{chapter.filename}">{xml_escape(chapter.title)}</a></li>' for chapter in chapters
    )
    entries["EPUB/nav.xhtml"] = xhtml_document(
        "Contents",
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + nav_items
        + '<li><a href="colophon.xhtml">Source and edition notes</a></li></ol></nav>',
        body_class="navigation",
    )
    ncx_points = "".join(
        f'<navPoint id="nav-{index}" playOrder="{index}"><navLabel><text>{xml_escape(chapter.title)}</text></navLabel><content src="{chapter.filename}" /></navPoint>'
        for index, chapter in enumerate(chapters, start=1)
    )
    entries["EPUB/toc.ncx"] = f'''<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="{xml_escape(work['id'], quote=True)}" /></head><docTitle><text>{xml_escape(title)}</text></docTitle><navMap>{ncx_points}</navMap></ncx>
'''.encode("utf-8")

    author_metadata = "".join(f'<dc:creator>{xml_escape(name)}</dc:creator>' for name in author_names)
    chapter_manifest = "".join(
        f'<item id="chapter-{index}" href="{chapter.filename}" media-type="application/xhtml+xml" />'
        for index, chapter in enumerate(chapters, start=1)
    )
    chapter_spine = "".join(f'<itemref idref="chapter-{index}" />' for index in range(1, len(chapters) + 1))
    image_manifest = "".join(
        f'<item id="image-{index}" href="{xml_escape(asset_hrefs[asset["id"]], quote=True)}" media-type="{xml_escape(asset.get("mime_type") or mimetypes.guess_type(asset_hrefs[asset["id"]])[0] or "application/octet-stream", quote=True)}" />'
        for index, asset in enumerate(stored_assets, start=1)
    )
    entries["EPUB/package.opf"] = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="{OPF_NAMESPACE}" version="3.0" unique-identifier="publication-id" xml:lang="ja" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
<metadata xmlns:dc="{DC_NAMESPACE}"><dc:identifier id="publication-id">{xml_escape(work['id'])}</dc:identifier><dc:title>{xml_escape(title)}</dc:title><dc:language>ja</dc:language>{author_metadata}<dc:source>{xml_escape(work['source'].get('card_url'))}</dc:source><dc:rights>Public-domain text distributed by Aozora Bunko</dc:rights><meta property="dcterms:modified">{modified_timestamp(work)}</meta><meta property="rendition:layout">reflowable</meta><meta property="rendition:writing-mode">vertical-rl</meta></metadata>
<manifest><item id="cover" href="cover.xhtml" media-type="application/xhtml+xml" /><item id="cover-image" href="images/cover.svg" media-type="image/svg+xml" properties="cover-image" /><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" /><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" /><item id="css" href="styles/book.css" media-type="text/css" />{chapter_manifest}<item id="colophon" href="colophon.xhtml" media-type="application/xhtml+xml" />{image_manifest}</manifest>
<spine toc="ncx" page-progression-direction="rtl"><itemref idref="cover" linear="no" />{chapter_spine}<itemref idref="colophon" /></spine>
</package>
'''.encode("utf-8")

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        add_entry(archive, "mimetype", b"application/epub+zip", stored=True)
        for name in sorted(entries):
            add_entry(archive, name, entries[name])
    return stream.getvalue()


def resolve_epub_href(base: str, href: str) -> str:
    path = unquote(urlsplit(href).path)
    if not path:
        return base
    return str(PurePosixPath(base).parent.joinpath(path))


def validate_epub_bytes(payload: bytes, *, expected_identifier: str | None = None) -> dict[str, int]:
    errors: list[str] = []
    spine_paths: list[str] = []
    nav_path = ""
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise ValueError(f"invalid EPUB ZIP: {error}") from error
    with archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if not infos or infos[0].filename != "mimetype":
            errors.append("mimetype must be the first ZIP entry")
        elif infos[0].compress_type != zipfile.ZIP_STORED:
            errors.append("mimetype must be stored without compression")
        if len(names) != len(set(names)):
            errors.append("duplicate ZIP entries")
        if "mimetype" not in names or archive.read("mimetype") != b"application/epub+zip":
            errors.append("invalid mimetype payload")
        try:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(f".//{{{CONTAINER_NAMESPACE}}}rootfile")
            package_path = rootfile.attrib["full-path"] if rootfile is not None else ""
        except (KeyError, ElementTree.ParseError) as error:
            errors.append(f"invalid container.xml: {error}")
            package_path = ""
        if not package_path or package_path not in names:
            errors.append("container rootfile is missing")
        else:
            try:
                package = ElementTree.fromstring(archive.read(package_path))
            except ElementTree.ParseError as error:
                errors.append(f"invalid package document: {error}")
                package = None
            if package is not None:
                metadata = package.find(f"{{{OPF_NAMESPACE}}}metadata")
                manifest = package.find(f"{{{OPF_NAMESPACE}}}manifest")
                spine = package.find(f"{{{OPF_NAMESPACE}}}spine")
                if metadata is None or manifest is None or spine is None:
                    errors.append("package requires metadata, manifest, and spine")
                else:
                    required = {
                        "identifier": metadata.find(f"{{{DC_NAMESPACE}}}identifier"),
                        "title": metadata.find(f"{{{DC_NAMESPACE}}}title"),
                        "language": metadata.find(f"{{{DC_NAMESPACE}}}language"),
                    }
                    for field, element in required.items():
                        if element is None or not (element.text or "").strip():
                            errors.append(f"missing dc:{field}")
                    identifier = required["identifier"]
                    if expected_identifier and identifier is not None and identifier.text != expected_identifier:
                        errors.append("publication identifier does not match work")
                    modified = metadata.find(f"{{{OPF_NAMESPACE}}}meta[@property='dcterms:modified']")
                    if modified is None or not (modified.text or "").strip():
                        errors.append("missing dcterms:modified")
                    items = manifest.findall(f"{{{OPF_NAMESPACE}}}item")
                    item_ids = [item.attrib.get("id", "") for item in items]
                    if len(item_ids) != len(set(item_ids)):
                        errors.append("duplicate manifest IDs")
                    package_dir = str(PurePosixPath(package_path).parent)
                    manifest_paths: dict[str, str] = {}
                    nav_count = 0
                    for item in items:
                        href = item.attrib.get("href", "")
                        target = str(PurePosixPath(package_dir) / href)
                        manifest_paths[item.attrib.get("id", "")] = target
                        if target not in names:
                            errors.append(f"missing manifest resource: {target}")
                        if "nav" in item.attrib.get("properties", "").split():
                            nav_count += 1
                            nav_path = target
                    if nav_count != 1:
                        errors.append("manifest must contain exactly one navigation document")
                    for itemref in spine.findall(f"{{{OPF_NAMESPACE}}}itemref"):
                        idref = itemref.attrib.get("idref")
                        if idref not in manifest_paths:
                            errors.append(f"spine references unknown item: {itemref.attrib.get('idref')}")
                        elif itemref.attrib.get("linear", "yes") != "no":
                            spine_paths.append(manifest_paths[idref])

        xhtml_files = [name for name in names if name.endswith(".xhtml")]
        for name in xhtml_files:
            try:
                document = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError as error:
                errors.append(f"invalid XHTML {name}: {error}")
                continue
            if document.tag != f"{{{XHTML_NAMESPACE}}}html":
                errors.append(f"XHTML namespace missing in {name}")
            for element in document.iter():
                source = element.attrib.get("src")
                if source:
                    if urlsplit(source).scheme:
                        errors.append(f"remote runtime asset in {name}: {source}")
                    elif resolve_epub_href(name, source) not in names:
                        errors.append(f"missing referenced asset in {name}: {source}")
                href = element.attrib.get("href")
                if href and not urlsplit(href).scheme:
                    target = resolve_epub_href(name, href)
                    if target not in names:
                        errors.append(f"missing local link target in {name}: {href}")
        if nav_path in names:
            navigation = ElementTree.fromstring(archive.read(nav_path))
            nav_links = [
                resolve_epub_href(nav_path, element.attrib["href"])
                for element in navigation.iter(f"{{{XHTML_NAMESPACE}}}a")
                if element.attrib.get("href") and not urlsplit(element.attrib["href"]).scheme
            ]
            if nav_links != spine_paths:
                errors.append("navigation order does not match the linear spine")
        if errors:
            raise ValueError("; ".join(errors))
        return {"entries": len(names), "xhtml": len(xhtml_files)}


def validate_epub(path: Path, *, expected_identifier: str | None = None) -> dict[str, int]:
    return validate_epub_bytes(path.read_bytes(), expected_identifier=expected_identifier)


def write_bytes_if_changed(path: Path, payload: bytes) -> tuple[str, bool]:
    checksum = hashlib.sha256(payload).hexdigest()
    if path.is_file() and path.read_bytes() == payload:
        return checksum, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return checksum, True


def build_epubs(catalog_dir: Path, output_dir: Path) -> dict[str, Any]:
    catalog = json.loads((catalog_dir / "indexes" / "catalog.json").read_text(encoding="utf-8"))
    author_index = json.loads((catalog_dir / "indexes" / "authors.json").read_text(encoding="utf-8"))
    authors = {author["id"]: author for author in author_index["authors"]}
    download_dir = output_dir / "downloads"
    generated = 0
    unchanged = 0
    failed = 0
    outputs: dict[str, str] = {}
    expected: set[str] = set()
    for catalog_work in catalog["works"]:
        raw_id = catalog_work["id"].rsplit(":", 1)[-1]
        work = json.loads((catalog_dir / "works" / f"{raw_id}.json").read_text(encoding="utf-8"))
        work_authors = [authors[author_id] for author_id in work["author_ids"]]
        filename = export_filename(work, work_authors, "epub")
        expected.add(filename)
        destination = download_dir / filename
        error_marker = download_dir / f"{filename}.error.txt"
        try:
            payload = build_epub(work, work_authors, catalog_dir)
            validation = validate_epub_bytes(payload, expected_identifier=work["id"])
            checksum, changed = write_bytes_if_changed(destination, payload)
            if error_marker.is_file():
                error_marker.unlink()
            generated += int(changed)
            unchanged += int(not changed)
            outputs[f"downloads/{filename}"] = checksum
            outputs[f"validation/{filename}"] = f'{validation["entries"]}:{validation["xhtml"]}'
        except Exception as error:  # preserve per-work failure diagnostics without hiding other books
            failed += 1
            if destination.is_file():
                destination.unlink()
            write_bytes_if_changed(error_marker, (str(error) + "\n").encode("utf-8"))
    if download_dir.is_dir():
        for path in download_dir.glob("*.epub"):
            if path.name not in expected:
                path.unlink()
    manifest = {
        "schema_version": 1,
        "generator_version": EPUB_GENERATOR_VERSION,
        "work_count": len(catalog["works"]),
        "failed": failed,
        "outputs": dict(sorted(outputs.items())),
    }
    manifest_path = output_dir / "epub-manifest.json"
    write_bytes_if_changed(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return {"works": len(catalog["works"]), "generated": generated, "unchanged": unchanged, "failed": failed}
