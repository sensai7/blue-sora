"""Validate generated HTML, accessibility basics, assets, and design tokens."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.site_validation import audit_html, contrast_ratio


FINGERPRINT_RE = re.compile(r"\.[0-9a-f]{12}\.(?:css|js|svg|json)$")
ROOT_RELATIVE_RE = re.compile(r'(?:href|src|action|data-library-url)="/(?!/)')


def resolve_local_url(site: Path, page: Path, url: str) -> Path:
    path = unquote(urlsplit(url).path)
    candidate = site / path.lstrip("/") if path.startswith("/") else page.parent / path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(site.resolve())
    except ValueError as error:
        raise SystemExit(f"{page}: local URL escapes the site artifact: {url}") from error
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("build/site"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads((args.site / "site-manifest.json").read_text(encoding="utf-8"))
    html_paths = sorted(args.site.rglob("*.html"))
    if not html_paths:
        raise SystemExit("No generated HTML pages found")
    placeholder_count = 0
    work_page_count = 0
    epub_download_count = 0
    pdf_download_count = 0
    rendered_image_count = 0
    for path in html_paths:
        source_html = path.read_text(encoding="utf-8")
        if ROOT_RELATIVE_RE.search(source_html):
            raise SystemExit(f"{path}: root-relative URL is not portable to a GitHub project site")
        audit = audit_html(path)
        errors = audit.results()
        if errors:
            raise SystemExit(f"{path}: {'; '.join(errors)}")
        placeholder_count += audit.cover_placeholders
        if path.parent.parent.name == "works":
            work_page_count += 1
            html = source_html
            for required in ('data-reader', 'id="read-here"', 'class="reader-content"', 'Difficulty statistics'):
                if required not in html:
                    raise SystemExit(f"{path}: missing reader structure: {required}")
            expected_epub = f'../../downloads/{path.parent.name}.epub'
            if f'href="{expected_epub}"' not in html or "Download EPUB" not in html:
                raise SystemExit(f"{path}: missing EPUB download control: {expected_epub}")
            if not resolve_local_url(args.site, path, expected_epub).is_file():
                raise SystemExit(f"{path}: EPUB download target is missing: {expected_epub}")
            epub_download_count += 1
            expected_pdf = f'../../downloads/{path.parent.name}.pdf'
            if f'href="{expected_pdf}"' in html:
                if not resolve_local_url(args.site, path, expected_pdf).is_file():
                    raise SystemExit(f"{path}: PDF download target is missing: {expected_pdf}")
                pdf_download_count += 1
            else:
                error_marker = args.site / "downloads" / f"{path.parent.name}.pdf.error.txt"
                if "Download PDF" not in html or "PDF generation failed" not in html or not error_marker.is_file():
                    raise SystemExit(f"{path}: missing PDF download control: {expected_pdf}")
        for url in audit.asset_urls:
            if url.startswith(("http://", "https://")):
                raise SystemExit(f"{path}: remote runtime asset {url}")
            if not FINGERPRINT_RE.search(url):
                raise SystemExit(f"{path}: asset is not fingerprinted: {url}")
            if not resolve_local_url(args.site, path, url).is_file():
                raise SystemExit(f"{path}: missing local asset: {url}")
        for url in audit.image_urls:
            if url.startswith(("http://", "https://")):
                raise SystemExit(f"{path}: remote reader image {url}")
            if not resolve_local_url(args.site, path, url).is_file():
                raise SystemExit(f"{path}: missing reader image: {url}")
            rendered_image_count += 1
    if placeholder_count == 0:
        raise SystemExit("No empty cover placeholder was generated")
    if work_page_count != manifest.get("work_count"):
        raise SystemExit(f"Expected {manifest.get('work_count')} work pages, found {work_page_count}")

    for relative_path, expected_hash in manifest["outputs"].items():
        path = args.site / relative_path
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise SystemExit(f"Missing or changed generated output: {relative_path}")
    css = (args.site / manifest["assets"]["css"].lstrip("/")).read_text(encoding="utf-8")
    for required in ("@media (max-width: 64rem)", "@media (max-width: 42rem)", "prefers-reduced-motion", "book-cover--empty"):
        if required not in css:
            raise SystemExit(f"Missing design-system rule: {required}")
    if contrast_ratio("#111827", "#f4f0e7") < 4.5 or contrast_ratio("#ffffff", "#1d4ed8") < 4.5:
        raise SystemExit("Core foreground/background tokens fail WCAG AA contrast")
    library = json.loads((args.site / manifest["assets"]["library"].lstrip("/")).read_text(encoding="utf-8"))
    if len(library.get("works", [])) != manifest.get("work_count"):
        raise SystemExit("Library index does not expose every catalog work")
    if any(not work.get("search") or not work.get("authors") for work in library["works"]):
        raise SystemExit("Library index contains an unsearchable work")
    print(f"Validated HTML pages: {len(html_paths)}")
    print(f"Accessible cover placeholders: {placeholder_count}")
    print(f"Validated output hashes: {len(manifest['outputs'])}")
    print("Remote runtime assets: 0")
    print("Core color contrast: WCAG AA")
    print(f"Browsable catalog works: {len(library['works'])}")
    print(f"Complete work pages: {work_page_count}")
    print(f"Working EPUB downloads: {epub_download_count}")
    print(f"Working PDF downloads: {pdf_download_count}")
    print(f"Local reader images: {rendered_image_count}")


if __name__ == "__main__":
    main()
