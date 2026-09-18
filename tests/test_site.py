from __future__ import annotations

import unittest
from pathlib import Path

from blue_sora.site import build_library_index, literary_era
from blue_sora.site_validation import PageAudit, contrast_ratio


class SiteTests(unittest.TestCase):
    def test_core_color_pairs_pass_wcag_aa(self) -> None:
        self.assertGreaterEqual(contrast_ratio("#111827", "#f4f0e7"), 4.5)
        self.assertGreaterEqual(contrast_ratio("#ffffff", "#1d4ed8"), 4.5)

    def test_accessibility_audit_reports_missing_structure(self) -> None:
        parser = PageAudit()
        parser.feed("<html><head><title></title></head><body><img src='x'></body></html>")
        errors = parser.results()
        self.assertIn("missing HTML5 doctype", errors)
        self.assertIn("image is missing alt text", errors)
        self.assertIn("page must contain exactly one main landmark", errors)

    def test_generated_home_has_black_cover_component(self) -> None:
        html = Path("build/site/index.html").read_text(encoding="utf-8")
        self.assertIn("book-cover--empty", html)
        css = next(Path("build/site/assets").glob("styles.*.css")).read_text(encoding="utf-8")
        self.assertIn(".book-cover--empty { background: #050505; }", css)

    def test_generated_catalog_links_to_work_pages(self) -> None:
        html = Path("build/site/index.html").read_text(encoding="utf-8")
        self.assertIn('works/aozora-000386/index.html', html)
        self.assertTrue(Path("build/site/works/aozora-000386/index.html").is_file())

    def test_literary_era_uses_author_lifespan(self) -> None:
        self.assertEqual(literary_era("1901-02-03"), "Meiji")
        self.assertEqual(literary_era("1924-01-01"), "Taisho")
        self.assertEqual(literary_era("1965-07-28"), "Showa")
        self.assertEqual(literary_era(None), "Unknown")

    def test_library_index_contains_search_and_filter_fields(self) -> None:
        works = [{
            "id": "work:1", "slug": "sample", "title": "人間椅子", "title_reading": "にんげんいす",
            "authors": [{"id": "author:1", "name": "江戸川乱歩", "romanized": "Ranpo Edogawa"}],
            "metrics": {"length_words": 1200}, "difficulty": {"average_difficulty": 42, "status": "scored"},
            "orthography": "新字新仮名", "has_illustrations": True,
        }]
        authors = [{
            "id": "author:1", "death_date": "1965-07-28",
            "name": {"display": "江戸川乱歩", "reading": "えどがわらんぽ", "romanized": "Ranpo Edogawa"},
        }]
        record = build_library_index(works, authors)["works"][0]
        self.assertIn("人間椅子", record["search"])
        self.assertIn("Ranpo Edogawa", record["search"])
        self.assertEqual(record["eras"], ["Showa"])
        self.assertTrue(record["illustrations"])


if __name__ == "__main__":
    unittest.main()
