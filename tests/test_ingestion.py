from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from blue_sora.ingestion import canonical_text, download_assets, ingest_work, render_blocks


FIXTURE = Path(__file__).parent / "fixtures" / "representative.html"


class IngestionTests(unittest.TestCase):
    def document(self) -> dict:
        source = FIXTURE.read_text(encoding="utf-8").encode("cp932")
        return ingest_work(
            source,
            {"作品ID": "000001", "作品名": "試験"},
            source_filename="000001.html",
            source_url="https://www.aozora.gr.jp/cards/000001/files/000001.html",
        )

    def test_separates_sections_and_normalizes_markup(self) -> None:
        document = self.document()
        body = document["content"]["body"]
        self.assertEqual(body[0]["type"], "heading")
        self.assertEqual(body[0]["level"], 2)
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertIn('"type": "ruby"', serialized)
        self.assertIn('"reading": "あおぞら"', serialized)
        self.assertIn('"type": "warichu"', serialized)
        self.assertEqual(document["content"]["bibliography"][0]["type"], "list")
        self.assertEqual(document["content"]["notation_notes"][0]["type"], "table")

    def test_content_uses_asset_ids_not_remote_urls(self) -> None:
        document = self.document()
        content = json.dumps(document["content"], ensure_ascii=False)
        self.assertNotIn("aozora.gr.jp", content)
        self.assertEqual(len(document["assets"]), 2)
        self.assertTrue(all(asset["local_path"].startswith("assets/") for asset in document["assets"]))

    def test_unknown_markup_is_preserved_and_reported(self) -> None:
        document = self.document()
        self.assertTrue(any(item["code"] == "unrecognized_markup" for item in document["warnings"]))
        self.assertIn("source_markup", json.dumps(document["content"]))

    def test_source_text_integrity_has_no_loss(self) -> None:
        document = self.document()
        self.assertFalse(any(item["code"] == "text_loss" for item in document["warnings"]))
        self.assertIn("第一章", canonical_text(document["content"]["body"]))

    def test_rendering_matches_snapshot(self) -> None:
        document = self.document()
        rendered = render_blocks(document["content"]["body"], document["assets"])
        expected = (Path(__file__).parent / "snapshots" / "representative.html").read_text(encoding="utf-8").rstrip("\n")
        self.assertEqual(rendered, expected)

    def test_output_is_deterministic(self) -> None:
        first = json.dumps(self.document(), ensure_ascii=False, sort_keys=True)
        second = json.dumps(self.document(), ensure_ascii=False, sort_keys=True)
        self.assertEqual(first, second)

    def test_download_records_provenance_and_errors(self) -> None:
        document = self.document()
        calls = 0

        def fetcher(url: str) -> tuple[bytes, str | None]:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("fixture failure")
            return b"PNG fixture", "image/png"

        output = Path("build/test-assets")
        for asset in document["assets"]:
            (output / asset["local_path"]).unlink(missing_ok=True)
        download_assets(document, output, fetcher)
        stored = [asset for asset in document["assets"] if asset["status"] == "stored"]
        failed = [asset for asset in document["assets"] if asset["status"] == "error"]
        self.assertEqual((len(stored), len(failed)), (1, 1))
        self.assertEqual(stored[0]["sha256"], hashlib.sha256(b"PNG fixture").hexdigest())
        self.assertIn("fixture failure", failed[0]["diagnostic"])

    def test_download_reuses_cached_asset(self) -> None:
        document = self.document()
        output = Path("build/test-cache")
        first_asset = document["assets"][0]
        destination = output / first_asset["local_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"cached image")

        def should_not_fetch(url: str) -> tuple[bytes, str | None]:
            raise AssertionError(f"unexpected request: {url}")

        download_assets({"assets": [first_asset]}, output, should_not_fetch)
        self.assertEqual(first_asset["status"], "stored")
        self.assertEqual(first_asset["sha256"], hashlib.sha256(b"cached image").hexdigest())


if __name__ == "__main__":
    unittest.main()
