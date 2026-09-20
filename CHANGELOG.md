# Changelog

All notable user-facing and build changes are recorded here.

## Unreleased

- Expanded the reduced Aozora Bunko corpus to 1,061 public-domain works from
  14 authors, and regenerated the catalog, site, EPUB, and PDF artifacts.
- Made Shift-JIS ingestion tolerant of isolated invalid bytes in source notes.
- Added non-Jōyō kanji occurrence counts and 90th-percentile sentence length
  to learner metrics, with definitions and explanatory labels in work pages.
- Improved title sorting by ignoring opening Japanese quote marks.
- Rendered gaiji correctly when used as the base text of PDF ruby annotations.
- Recorded unavailable download assets as `pending` or `error` instead of
  requiring every provenance record to be stored.
