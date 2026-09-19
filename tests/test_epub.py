from __future__ import annotations

import json
import shutil
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from blue_sora.epub import build_epub, build_epubs, split_chapters, validate_epub_bytes


def sample_work() -> dict:
    return {
        "id": "aozora:work:000001",
        "slug": "aozora-000001",
        "title": {"display": "青空", "reading": "あおぞら", "subtitle": None},
        "author_ids": ["aozora:person:000001"],
        "published_at": "2026-01-02",
        "assets": [{
            "id": "image-1", "kind": "illustration", "status": "stored",
            "build_path": "canonical/assets/image-1.png", "mime_type": "image/png",
        }],
        "content": {
            "body": [
                {"type": "heading", "level": 2, "inlines": [{"type": "text", "text": "第一章"}]},
                {"type": "paragraph", "inlines": [
                    {"type": "ruby", "base": [{"type": "text", "text": "青空"}], "reading": "あおぞら"},
                    {"type": "illustration", "asset_id": "image-1", "alt": "挿絵"},
                ]},
                {"type": "heading", "level": 2, "inlines": [{"type": "text", "text": "第二章"}]},
                {"type": "paragraph", "inlines": [{"type": "text", "text": "終"}]},
            ],
            "notation_notes": [],
            "bibliography": [{"type": "paragraph", "inlines": [{"type": "text", "text": "底本情報"}]}],
        },
        "source": {"card_url": "https://www.aozora.gr.jp/cards/000001/card1.html"},
    }


def sample_author() -> dict:
    return {"id": "aozora:person:000001", "name": {"display": "著者", "romanized": "Author"}}


class EpubTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = Path("build/test-epub-tests")
        if self.temporary.exists():
            shutil.rmtree(self.temporary)
        self.temporary.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.temporary.exists():
            shutil.rmtree(self.temporary)

    def test_chapters_follow_source_heading_order(self) -> None:
        chapters = split_chapters(sample_work()["content"]["body"])
        self.assertEqual([chapter.title for chapter in chapters], ["第一章", "第二章"])
        self.assertEqual([chapter.filename for chapter in chapters], ["chapter-001.xhtml", "chapter-002.xhtml"])

    def test_epub_is_deterministic_valid_and_self_contained(self) -> None:
        catalog = self.temporary / "catalog"
        asset = self.temporary / "canonical" / "assets" / "image-1.png"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        first = build_epub(sample_work(), [sample_author()], catalog)
        second = build_epub(sample_work(), [sample_author()], catalog)
        self.assertEqual(first, second)
        result = validate_epub_bytes(first, expected_identifier="aozora:work:000001")
        self.assertGreaterEqual(result["xhtml"], 5)
        with zipfile.ZipFile(BytesIO(first)) as archive:
            self.assertEqual(archive.infolist()[0].filename, "mimetype")
            self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)
            chapter = archive.read("EPUB/chapter-001.xhtml").decode("utf-8")
            self.assertIn("<ruby>青空<rt>あおぞら</rt></ruby>", chapter)
            self.assertIn('src="images/image-1.png"', chapter)
            package = archive.read("EPUB/package.opf").decode("utf-8")
            self.assertIn('page-progression-direction="rtl"', package)
            self.assertIn("Public-domain text distributed by Aozora Bunko", package)

    def test_full_builder_caches_unchanged_book(self) -> None:
        root = self.temporary
        catalog = root / "catalog"
        (catalog / "indexes").mkdir(parents=True)
        (catalog / "works").mkdir()
        asset = root / "canonical" / "assets" / "image-1.png"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        work = sample_work()
        (catalog / "indexes" / "catalog.json").write_text(
            json.dumps({"works": [{"id": work["id"], "slug": work["slug"]}]}), encoding="utf-8"
        )
        (catalog / "indexes" / "authors.json").write_text(
            json.dumps({"authors": [sample_author()]}), encoding="utf-8"
        )
        (catalog / "works" / "000001.json").write_text(json.dumps(work), encoding="utf-8")
        output = root / "site"
        first = build_epubs(catalog, output)
        second = build_epubs(catalog, output)
        self.assertEqual(first["generated"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(second["failed"], 0)
        self.assertTrue((output / "downloads" / "著者-青空-aozora-000001.epub").is_file())


if __name__ == "__main__":
    unittest.main()
