from __future__ import annotations

import unittest

from blue_sora.joyo import ELEMENTARY_KANJI_BY_GRADE, JOYO_KANJI


class JoyoTests(unittest.TestCase):
    def test_current_elementary_allocation_is_complete_and_disjoint(self) -> None:
        expected_counts = [80, 160, 200, 202, 193, 191]
        self.assertEqual([len(group) for group in ELEMENTARY_KANJI_BY_GRADE], expected_counts)
        elementary = "".join(ELEMENTARY_KANJI_BY_GRADE)
        self.assertEqual(len(elementary), 1026)
        self.assertEqual(len(set(elementary)), 1026)
        self.assertTrue(set(elementary).issubset(JOYO_KANJI))


if __name__ == "__main__":
    unittest.main()
