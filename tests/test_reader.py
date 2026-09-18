from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from blue_sora.reader import export_state, render_blocks


class ReaderTests(unittest.TestCase):
    def test_renderer_preserves_semantic_inline_content(self) -> None:
        blocks = [
            {
                "type": "heading",
                "level": 2,
                "inlines": [{"type": "text", "text": "第一章"}],
            },
            {
                "type": "paragraph",
                "inlines": [
                    {"type": "ruby", "base": [{"type": "text", "text": "青空"}], "reading": "あおぞら"},
                    {"type": "emphasis", "style": "sesame_dot", "children": [{"type": "text", "text": "強調"}]},
                    {"type": "note", "children": [{"type": "text", "text": "注記"}]},
                    {"type": "anchor", "id": "spot", "children": [{"type": "text", "text": "位置"}]},
                    {"type": "illustration", "asset_id": "image-1", "alt": "挿絵"},
                ],
            },
        ]
        rendered = render_blocks(blocks, {"image-1": "/media/image-1.png"}, collect_toc=True)
        markup = str(rendered.html)
        self.assertIn("<ruby>青空<rt>あおぞら</rt></ruby>", markup)
        self.assertIn('role="note"', markup)
        self.assertIn('id="spot"', markup)
        self.assertIn('src="/media/image-1.png"', markup)
        self.assertEqual(rendered.toc, [{"id": "section-1", "level": 2, "label": "第一章"}])

    def test_missing_image_has_accessible_fallback(self) -> None:
        blocks = [{"type": "paragraph", "inlines": [{"type": "illustration", "asset_id": "missing", "alt": "挿絵"}]}]
        markup = str(render_blocks(blocks, {}).html)
        self.assertIn('role="img"', markup)
        self.assertIn('aria-label="挿絵"', markup)

    def test_export_states_cover_available_unavailable_and_error(self) -> None:
        output = Path("build/site")
        with mock.patch("blue_sora.reader.Path.is_file", autospec=True, return_value=False):
            self.assertEqual(export_state(output, "sample", "epub")["status"], "unavailable")
        with mock.patch(
            "blue_sora.reader.Path.is_file",
            autospec=True,
            side_effect=lambda path: str(path).endswith("sample.epub"),
        ):
            self.assertEqual(export_state(output, "sample", "epub")["status"], "available")
        with mock.patch(
            "blue_sora.reader.Path.is_file",
            autospec=True,
            side_effect=lambda path: str(path).endswith("sample.pdf.error.txt"),
        ):
            self.assertEqual(export_state(output, "sample", "pdf")["status"], "error")


if __name__ == "__main__":
    unittest.main()
