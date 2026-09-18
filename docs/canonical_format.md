# Canonical Aozora format

Milestone 2 converts each source XHTML file into deterministic UTF-8 JSON.
The source remains immutable and every document records its source SHA-256,
decoder, parser version, filename, and canonical Aozora URL.

## Document shape

```text
schema_version
metadata                 original aozora.csv row
content
  body[]                 readable work blocks
  bibliography[]         source/edition information
  notation_notes[]       editorial notation notes
assets[]                 local cache records and source provenance
provenance               parser and source identity
warnings[]               explicit unsupported/missing markup diagnostics
```

Blocks are `heading`, `paragraph`, or `separator` values. Inline content uses
typed nodes for text, ruby, emphasis, warichu, notes, anchors, illustrations,
gaiji, superscript, subscript, small text, and named source styles. Lists and
gaiji tables retain their structure. Unknown markup is retained as
`source_markup` with its children and also emits an `unrecognized_markup`
warning.

Heading classes are normalized as follows:

| Source class | Canonical level |
|---|---:|
| `o-midashi` | 2 |
| `naka-midashi`, `mado-naka-midashi`, `dogyo-naka-midashi` | 3 |
| `ko-midashi`, `dogyo-ko-midashi` | 4 |

## Assets

Canonical content refers only to deterministic asset IDs. The asset manifest
keeps the original absolute URL, local relative path, kind, MIME type, byte
size, SHA-256, retrieval status, and diagnostic. This makes later HTML, EPUB,
and PDF generation independent of runtime Aozora access.

The downloader is resumable: an existing cache file is hashed and reused.
Retrieval failures are recorded on the asset without discarding the rest of
the work.

Run `scripts/validate_ingestion.py` after an asset-backed build to verify the
source/document set, zero unresolved diagnostics, local asset references,
cache checksums, and absence of remote image dependencies in rendered output.

## Current diagnostics

The initial full-corpus pass intentionally reports markup outside the first
canonical family. These warnings are the work queue for additional regression
fixtures; they must not be suppressed without either mapping or explicitly
preserving the source construct.
