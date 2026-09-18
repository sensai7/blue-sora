from __future__ import annotations

import json
import io
import shutil
import unittest
from pathlib import Path

import pdfplumber

from blue_sora.pdf import build_pdf, build_pdfs, validate_pdf_bytes


def sample_work() -> dict:
    return {
        "id": "aozora:work:000001",
        "aozora_work_id": "000001",
        "slug": "aozora-000001",
        "title": {"display": "青空", "reading": "あおぞら", "subtitle": None},
        "author_ids": ["aozora:person:000001"],
        "published_at": "2026-01-02",
        "orthography": "新字新仮名",
        "assets": [{
            "id": "image-1", "kind": "illustration", "status": "stored",
            "build_path": "canonical/assets/image-1.png", "mime_type": "image/png",
        }],
        "content": {
            "body": [
                {"type": "heading", "level": 2, "inlines": [{"type": "text", "text": "第一章"}]},
                {"type": "paragraph", "inlines": [
                    {"type": "ruby", "base": [{"type": "text", "text": "青空"}], "reading": "あおぞら"},
                    {"type": "text", "text": "を読む。"},
                ]},
                {"type": "paragraph", "inlines": [{"type": "illustration", "asset_id": "image-1", "alt": "挿絵"}]},
            ],
            "notation_notes": [],
            "bibliography": [{"type": "paragraph", "inlines": [{"type": "text", "text": "底本情報"}]}],
        },
        "source": {"card_url": "https://www.aozora.gr.jp/cards/000001/card1.html"},
    }


def sample_author() -> dict:
    return {"id": "aozora:person:000001", "name": {"display": "著者", "romanized": "Author"}}


class PdfTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = Path("build/test-pdf-tests")
        if self.temporary.exists():
            shutil.rmtree(self.temporary)
        self.temporary.mkdir(parents=True)
        self.catalog = self.temporary / "catalog"
        asset = self.temporary / "canonical" / "assets" / "image-1.png"
        asset.parent.mkdir(parents=True)
        # A valid 2x2 RGB PNG generated once for this fixture.
        from PIL import Image
        Image.new("RGB", (2, 2), "#1d4ed8").save(asset)

    def tearDown(self) -> None:
        if self.temporary.exists():
            shutil.rmtree(self.temporary)

    def test_pdf_is_deterministic_searchable_and_embeds_fonts_and_images(self) -> None:
        first = build_pdf(sample_work(), [sample_author()], self.catalog)
        second = build_pdf(sample_work(), [sample_author()], self.catalog)
        self.assertEqual(first, second)
        result = validate_pdf_bytes(first, sample_work())
        self.assertGreaterEqual(result["pages"], 3)
        self.assertGreater(result["fonts"], 0)
        self.assertGreater(result["images"], 0)

    def test_ruby_reading_is_centered_above_the_complete_base_word(self) -> None:
        payload = build_pdf(sample_work(), [sample_author()], self.catalog)
        with pdfplumber.open(io.BytesIO(payload)) as document:
            body_characters = document.pages[1].chars
        base = [
            character for character in body_characters
            if character["text"] in "青空" and abs(float(character["size"]) - 10.5) < 0.1
        ]
        reading = [
            character for character in body_characters
            if character["text"] in "あおぞら" and abs(float(character["size"]) - 5.0) < 0.1
        ]
        self.assertEqual("".join(character["text"] for character in base), "青空")
        self.assertEqual("".join(character["text"] for character in reading), "あおぞら")
        base_center = (min(character["x0"] for character in base) + max(character["x1"] for character in base)) / 2
        reading_center = (
            min(character["x0"] for character in reading) + max(character["x1"] for character in reading)
        ) / 2
        self.assertAlmostEqual(base_center, reading_center, delta=0.2)
        self.assertLess(max(character["bottom"] for character in reading), min(character["top"] for character in base))

    def test_full_builder_caches_unchanged_pdf(self) -> None:
        (self.catalog / "indexes").mkdir(parents=True)
        (self.catalog / "works").mkdir()
        work = sample_work()
        (self.catalog / "indexes" / "catalog.json").write_text(
            json.dumps({"works": [{"id": work["id"], "slug": work["slug"]}]}), encoding="utf-8"
        )
        (self.catalog / "indexes" / "authors.json").write_text(
            json.dumps({"authors": [sample_author()]}), encoding="utf-8"
        )
        (self.catalog / "works" / "000001.json").write_text(json.dumps(work), encoding="utf-8")
        output = self.temporary / "site"
        first = build_pdfs(self.catalog, output)
        second = build_pdfs(self.catalog, output)
        self.assertEqual(first["generated"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(second["failed"], 0)


if __name__ == "__main__":
    unittest.main()
