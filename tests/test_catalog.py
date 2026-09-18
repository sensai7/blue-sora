from __future__ import annotations

import unittest
from pathlib import Path

from blue_sora.catalog import (
    person_id, person_slug, validate_relations, validate_schema, work_id, work_slug,
    write_if_changed,
)


class CatalogTests(unittest.TestCase):
    def test_identifiers_are_stable_and_zero_padded(self) -> None:
        self.assertEqual(work_id("386"), "aozora:work:000386")
        self.assertEqual(work_slug("386"), "aozora-000386")
        self.assertEqual(person_id("64"), "aozora:person:000064")
        self.assertEqual(person_slug("64"), "aozora-person-000064")

    def test_broken_author_relation_fails_clearly(self) -> None:
        work = {"id": "aozora:work:000001", "slug": "aozora-000001", "author_ids": ["aozora:person:999999"]}
        with self.assertRaisesRegex(ValueError, "missing authors"):
            validate_relations([work], {})

    def test_missing_required_schema_field_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "validation failed"):
            validate_schema({"schema_version": 1}, "author.schema.json")

    def test_unchanged_json_is_not_rewritten(self) -> None:
        path = Path("build/test-catalog/cache.json")
        _, first_changed = write_if_changed(path, {"stable": "value"})
        first_mtime = path.stat().st_mtime_ns
        _, second_changed = write_if_changed(path, {"stable": "value"})
        self.assertTrue(first_changed or path.is_file())
        self.assertFalse(second_changed)
        self.assertEqual(path.stat().st_mtime_ns, first_mtime)


if __name__ == "__main__":
    unittest.main()
