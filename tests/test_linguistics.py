from __future__ import annotations

import unittest
from collections import Counter
import subprocess
import sys
from pathlib import Path

from blue_sora.linguistics import analyze_base, finalize, prose_text, split_sentences, tokenize


class LinguisticsTests(unittest.TestCase):
    def test_analysis_cli_has_an_active_entry_point(self) -> None:
        result = subprocess.run(
            [sys.executable, str(Path("scripts/analyze_difficulty.py")), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Generate versioned Japanese-learning metrics", result.stdout)

    def test_japanese_sentence_splitting(self) -> None:
        self.assertEqual(
            split_sentences("吾輩は猫である。名前はまだ無い！\n本当か？"),
            ["吾輩は猫である。", "名前はまだ無い！", "本当か？"],
        )

    def test_tokenizer_excludes_punctuation(self) -> None:
        tokens = tokenize("吾輩は猫である。")
        self.assertGreaterEqual(len(tokens), 5)
        self.assertNotIn("。", tokens)

    def test_prose_excludes_heading_note_and_ruby_reading(self) -> None:
        blocks = [
            {"type": "heading", "level": 2, "inlines": [{"type": "text", "text": "章題"}]},
            {"type": "paragraph", "inlines": [
                {"type": "ruby", "base": [{"type": "text", "text": "青空"}], "reading": "あおぞら"},
                {"type": "note", "children": [{"type": "text", "text": "編集注"}]},
            ]},
        ]
        self.assertEqual(prose_text(blocks), "青空")

    def test_metrics_are_deterministic_and_versioned(self) -> None:
        document = {
            "metadata": {"作品ID": "1"},
            "provenance": {"source_sha256": "a" * 64},
            "content": {"body": [{"type": "paragraph", "inlines": [{"type": "text", "text": "猫が歩く。犬も歩く。"}]}]},
        }
        base = analyze_base(document)
        words = Counter(base.words)
        kanji = Counter(base.kanji)
        first = finalize(base, words, kanji)
        second = finalize(base, words, kanji)
        self.assertEqual(first, second)
        self.assertEqual(first["model_version"], "blue-sora-difficulty-v1")
        self.assertEqual(first["metrics"]["characters"], 10)
        self.assertIsNone(first["difficulty"]["average_difficulty"])
        self.assertEqual(first["status"], "outlier")


if __name__ == "__main__":
    unittest.main()
