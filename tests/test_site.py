from __future__ import annotations

import json
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
        work_pages = sorted(Path("build/site/works").glob("*/index.html"))
        self.assertTrue(work_pages)
        relative_path = work_pages[0].as_posix().removeprefix("build/site/")
        self.assertIn(relative_path, html)

    def test_generated_work_metrics_have_explanatory_tooltips(self) -> None:
        html = Path("build/site/works/aozora-058039/index.html").read_text(encoding="utf-8")
        self.assertIn('title="Word tokens in the prose, excluding whitespace, punctuation, and symbols."', html)
        self.assertIn('title="Average number of word tokens in each non-empty sentence."', html)
        self.assertIn('title="Distinct normalized word lemmas used in the prose."', html)
        self.assertIn('title="The number of kanji occurrences outside the 2010 Jōyō Kanji list. Listed alternate forms are included."', html)
        self.assertEqual(html.count('<div title='), 15)
        self.assertIn("Difficulty weights: lexical rarity 55% · kanji rarity 25% · sentence complexity 20%", html)
        self.assertNotIn("weight 55%", html)

    def test_generated_work_page_includes_lazy_kanji_analysis_controls(self) -> None:
        html = Path("build/site/works/aozora-058039/index.html").read_text(encoding="utf-8")
        self.assertIn('data-kanji-analysis-trigger', html)
        self.assertIn('data-kanji-analysis-dialog', html)
        self.assertIn('id="kanji-analysis-dialog"', html)
        manifest = json.loads(Path("build/site/site-manifest.json").read_text(encoding="utf-8"))
        reference = manifest["assets"]["kanji_reference"]
        self.assertIn(reference, html)
        self.assertTrue((Path("build/site") / reference).is_file())

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
