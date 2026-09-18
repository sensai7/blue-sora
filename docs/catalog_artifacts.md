# Catalog artifacts

Milestone 4 merges canonical content, Aozora metadata, assets, diagnostics, and
learner analytics into cacheable JSON under `build/catalog`.

## Stable identity

- Works: `aozora:work:000386`, slug `aozora-000386`
- Authors: `aozora:person:000064`, slug `aozora-person-000064`

Identity and slugs derive only from permanent Aozora IDs. Japanese names,
readings, and Romanized display names remain separate presentation fields.

## Outputs

```text
build/catalog/
  works/                 complete work-detail records
  authors/               author records and work relations
  indexes/catalog.json   compact browsing/filter fields
  indexes/authors.json   complete author index
  indexes/search.json    normalized title/author search text
  build-manifest.json    input fingerprints and output SHA-256 values
```

Schemas in `schemas/catalog` define authors, work details (including editions,
assets, analytics, and diagnostics), catalog entries, and the build manifest.
The validator also checks cross-file relations and search/catalog coverage.

## Incremental and reproducible builds

Each work input fingerprint combines the catalog generator version, canonical
document bytes, and analysis bytes. Unchanged work details are loaded from the
cache without rewriting them. Aggregate files use canonical key ordering and
are likewise left untouched when their bytes have not changed.

The manifest contains no wall-clock timestamp. Its corpus fingerprint and
output hashes are therefore identical for unchanged inputs.
