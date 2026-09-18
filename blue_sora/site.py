"""Deterministic Jinja-based static site generation."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .catalog import write_if_changed
from .reader import export_state, render_blocks


SITE_GENERATOR_VERSION = "blue-sora-site-v3"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "templates"
ASSET_SOURCE_DIR = PROJECT_ROOT / "site_assets"


def environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def fingerprinted_asset(source: Path, output_dir: Path) -> tuple[str, str]:
    return fingerprinted_payload(source.name, source.read_bytes(), output_dir)


def fingerprinted_payload(name: str, payload: bytes, output_dir: Path) -> tuple[str, str]:
    digest = hashlib.sha256(payload).hexdigest()
    source = Path(name)
    destination_name = f"{source.stem}.{digest[:12]}{source.suffix}"
    destination = output_dir / "assets" / destination_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or destination.read_bytes() != payload:
        destination.write_bytes(payload)
    return f"assets/{destination_name}", digest


def literary_era(death_date: str | None) -> str:
    """Classify the author's principal historical era from available lifespan data."""
    if not death_date:
        return "Unknown"
    year = int(death_date[:4])
    if year <= 1912:
        return "Meiji"
    if year <= 1926:
        return "Taisho"
    return "Showa"


def build_library_index(works: list[dict[str, Any]], authors: list[dict[str, Any]]) -> dict[str, Any]:
    author_records = {author["id"]: author for author in authors}
    compact_works = []
    for work in works:
        work_authors = []
        eras = set()
        search_parts = [work["title"], work.get("title_reading") or ""]
        for author_ref in work["authors"]:
            author = author_records.get(author_ref["id"])
            display = author_ref["name"]
            romanized = author_ref.get("romanized") or ""
            reading = ""
            if author:
                display = author["name"]["display"]
                romanized = author["name"].get("romanized") or romanized
                reading = author["name"].get("reading") or ""
                eras.add(literary_era(author.get("death_date")))
            work_authors.append({"id": author_ref["id"], "name": display, "romanized": romanized})
            search_parts.extend((display, reading, romanized))
        compact_works.append(
            {
                "id": work["id"],
                "slug": work["slug"],
                "title": work["title"],
                "reading": work.get("title_reading") or "",
                "authors": work_authors,
                "search": " ".join(search_parts),
                "length": int(work["metrics"]["length_words"]),
                "difficulty": work["difficulty"]["average_difficulty"],
                "difficulty_status": work["difficulty"]["status"],
                "orthography": work.get("orthography") or "Unknown",
                "illustrations": bool(work.get("has_illustrations")),
                "eras": sorted(eras or {"Unknown"}),
            }
        )
    return {"schema_version": 1, "works": compact_works}


def render_page(template: str, destination: Path, **context: Any) -> tuple[str, bool]:
    payload = environment().get_template(template).render(**context).encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()
    if destination.is_file() and destination.read_bytes() == payload:
        return checksum, False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return checksum, True


def build_site(catalog_dir: Path, output_dir: Path) -> dict[str, Any]:
    catalog = json.loads((catalog_dir / "indexes" / "catalog.json").read_text(encoding="utf-8"))
    authors = json.loads((catalog_dir / "indexes" / "authors.json").read_text(encoding="utf-8"))
    css_url, css_hash = fingerprinted_asset(ASSET_SOURCE_DIR / "styles.css", output_dir)
    js_url, js_hash = fingerprinted_asset(ASSET_SOURCE_DIR / "app.js", output_dir)
    favicon_url, favicon_hash = fingerprinted_asset(ASSET_SOURCE_DIR / "favicon.svg", output_dir)
    library_index = build_library_index(catalog["works"], authors["authors"])
    library_payload = (json.dumps(library_index, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    library_url, library_hash = fingerprinted_payload("library.json", library_payload, output_dir)
    shared = {
        "css_url": css_url,
        "js_url": js_url,
        "favicon_url": favicon_url,
        "site_name": "Blue Sora",
        "generator_version": SITE_GENERATOR_VERSION,
    }
    works = catalog["works"]
    author_records = {author["id"]: author for author in authors["authors"]}
    outputs: dict[str, str] = {}
    written = 0
    pages = [
        (
            "index.html",
            output_dir / "index.html",
            {
                **shared,
                "page_title": "Japanese literature, made approachable",
                "page_description": "Explore public-domain Japanese literature with transparent learner-focused metrics.",
                "works": works[:6],
                "library_url": library_url,
                "authors": authors["authors"],
                "work_count": len(works),
                "author_count": len(authors["authors"]),
                "body_class": "home-page",
                "root_prefix": "",
            },
        ),
        (
            "design-system.html",
            output_dir / "design-system" / "index.html",
            {
                **shared,
                "page_title": "Design system",
                "page_description": "Blue Sora typography, colors, spacing, and reusable components.",
                "sample_work": works[0],
                "body_class": "design-system-page",
                "root_prefix": "../",
            },
        ),
        (
            "404.html",
            output_dir / "404.html",
            {
                **shared,
                "page_title": "Page not found",
                "page_description": "The requested Blue Sora page could not be found.",
                "body_class": "error-page",
                "root_prefix": "",
            },
        ),
    ]
    for template, destination, context in pages:
        checksum, changed = render_page(template, destination, **context)
        outputs[destination.relative_to(output_dir).as_posix()] = checksum
        written += changed

    media_outputs: dict[str, str] = {}
    work_page_count = 0
    for catalog_work in works:
        work_path = catalog_dir / "works" / f"{catalog_work['id'].rsplit(':', 1)[-1]}.json"
        work = json.loads(work_path.read_text(encoding="utf-8"))
        asset_urls: dict[str, str] = {}
        for asset in work["assets"]:
            if asset.get("status") != "stored" or not asset.get("build_path"):
                continue
            source = catalog_dir.parent / asset["build_path"]
            if not source.is_file():
                continue
            media_name = f"{asset['id']}{source.suffix.lower()}"
            destination = output_dir / "media" / media_name
            payload = source.read_bytes()
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.is_file() or destination.read_bytes() != payload:
                destination.write_bytes(payload)
            relative = destination.relative_to(output_dir).as_posix()
            asset_urls[asset["id"]] = f"../../{relative}"
            media_outputs[relative] = hashlib.sha256(payload).hexdigest()

        body = render_blocks(work["content"]["body"], asset_urls, collect_toc=True)
        notation_notes = render_blocks(work["content"]["notation_notes"], asset_urls)
        bibliography = render_blocks(work["content"]["bibliography"], asset_urls)
        destination = output_dir / "works" / work["slug"] / "index.html"
        checksum, changed = render_page(
            "work.html",
            destination,
            **shared,
            page_title=work["title"]["display"],
            page_description=f"Read {work['title']['display']} by "
            + ", ".join(author_records[author_id]["name"]["romanized"] for author_id in work["author_ids"]),
            body_class="work-page",
            root_prefix="../../",
            work=work,
            authors=[author_records[author_id] for author_id in work["author_ids"]],
            rendered_body=body.html,
            toc=body.toc if len(body.toc) >= 2 else [],
            rendered_notes=notation_notes.html,
            rendered_bibliography=bibliography.html,
            exports=[
                export_state(output_dir, work["slug"], "epub", "../../"),
                export_state(output_dir, work["slug"], "pdf", "../../"),
            ],
        )
        outputs[destination.relative_to(output_dir).as_posix()] = checksum
        written += changed
        work_page_count += 1
    outputs[css_url] = css_hash
    outputs[js_url] = js_hash
    outputs[favicon_url] = favicon_hash
    outputs[library_url] = library_hash
    outputs.update(media_outputs)
    for download in sorted((output_dir / "downloads").glob("*")):
        if download.suffix.lower() not in {".epub", ".pdf"}:
            continue
        payload = download.read_bytes()
        outputs[download.relative_to(output_dir).as_posix()] = hashlib.sha256(payload).hexdigest()
    for export_manifest_name in ("epub-manifest.json", "pdf-manifest.json"):
        export_manifest = output_dir / export_manifest_name
        if export_manifest.is_file():
            outputs[export_manifest_name] = hashlib.sha256(export_manifest.read_bytes()).hexdigest()

    nojekyll = output_dir / ".nojekyll"
    if not nojekyll.is_file() or nojekyll.read_bytes() != b"":
        nojekyll.write_bytes(b"")
    outputs[".nojekyll"] = hashlib.sha256(b"").hexdigest()

    expected_assets = {Path(css_url).name, Path(js_url).name, Path(favicon_url).name, Path(library_url).name}
    for path in (output_dir / "assets").glob("*"):
        if path.is_file() and path.name not in expected_assets:
            path.unlink()

    source_manifest = json.loads((catalog_dir / "build-manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 1,
        "generator_version": SITE_GENERATOR_VERSION,
        "catalog_fingerprint": source_manifest["corpus_fingerprint"],
        "work_count": len(works),
        "assets": {"css": css_url, "javascript": js_url, "favicon": favicon_url, "library": library_url},
        "outputs": dict(sorted(outputs.items())),
    }
    write_if_changed(output_dir / "site-manifest.json", manifest)
    return {
        "pages": len(pages) + work_page_count,
        "written": written,
        "works": len(works),
        "assets": 4,
        "media": len(media_outputs),
    }
