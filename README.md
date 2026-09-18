# Blue Sora

Blue Sora will generate a modern, English-friendly browser and reader for
Japanese literature from Aozora Bunko. The repository currently contains the
corpus preparation and quality-control tools used by the first milestone.

## Development corpus

The source metadata file is UTF-8 with a BOM. The source HTML is Shift-JIS
(JIS X 0208); the reduction script copies those files byte-for-byte.

```powershell
.\.venv\Scripts\python.exe scripts\create_reduced_corpus.py
.\.venv\Scripts\python.exe scripts\analyze_corpus.py
.\.venv\Scripts\python.exe scripts\inspect_html_formats.py
```

The checked-out full corpus has been filtered to works whose
`作品著作権フラグ` is `なし`. To audit or repeat that policy on a fresh corpus,
run the removal tool first without `--apply`; it defaults to a dry run:

```powershell
.\.venv\Scripts\python.exe scripts\remove_copyrighted_works.py
.\.venv\Scripts\python.exe scripts\remove_copyrighted_works.py --apply
```

The default reduced set includes works attributed to 江戸川乱歩, 福沢諭吉,
樋口夏子, or 樋口一葉. In the supplied metadata, all Natsuko Higuchi works
are catalogued under her pen name 樋口一葉.

See [the corpus format analysis](docs/corpus_format_analysis.md) and
[the project roadmap](docs/roadmap.md).

## Canonical ingestion

Build deterministic UTF-8 JSON documents from the reduced corpus:

```powershell
.\.venv\Scripts\python.exe scripts\ingest_corpus.py
.\.venv\Scripts\python.exe scripts\validate_ingestion.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pass `--download-assets` to cache illustrations and gaiji under the build
directory. Canonical content refers to local asset IDs; original URLs are kept
only in the asset provenance records. See
[the canonical format](docs/canonical_format.md) for the schema and
normalization rules.

## Linguistic analysis

Install the locked tokenizer and generate per-work learner metrics:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\analyze_difficulty.py
.\.venv\Scripts\python.exe scripts\validate_difficulty.py
```

Definitions, exclusions, and the versioned formula are documented in
[the difficulty model](docs/difficulty_model.md).

## Catalog artifacts

Merge canonical documents and learner analytics, then validate the complete
artifact graph:

```powershell
.\.venv\Scripts\python.exe scripts\build_catalog.py
.\.venv\Scripts\python.exe scripts\validate_catalog.py
```

See [the catalog artifact format](docs/catalog_artifacts.md) for schemas,
stable IDs, indexes, and incremental caching behavior.

## Static site

Build and validate the responsive site foundation:

```powershell
.\.venv\Scripts\python.exe scripts\build_site.py
.\.venv\Scripts\python.exe scripts\validate_site.py
```

The shared shell, responsive baseline, typography, accessibility rules, and
cover placeholder are documented in [the design system](docs/design_system.md).
Search, filter, sort, and pagination URL parameters are documented in
[the library browser contract](docs/library_browser.md).

Each catalog entry links to a complete static work page with source metadata,
learner metrics, normalized text, local images, reading-position persistence,
and export availability states. See [the online reader](docs/online_reader.md).

## EPUB downloads

`scripts/build_site.py` generates a deterministic EPUB 3 download for every
catalog work before rendering the work pages. EPUBs preserve chapter order,
ruby, illustrations, gaiji, source notes, and attribution, and use vertical
Japanese reading styles.

Run the EPUB stage and its conformance checks independently when needed:

```powershell
.\.venv\Scripts\python.exe scripts\build_epubs.py
.\.venv\Scripts\python.exe scripts\validate_epubs.py
```

See [the EPUB generation guide](docs/epub_generation.md) for package structure,
validation coverage, and reader compatibility notes.

## PDF downloads

The regular site build also generates print-ready A5 PDFs with searchable
Japanese text, embedded BIZ UD Mincho glyph subsets, source images, ruby
readings, bookmarks, page headers and footers, and explicit Aozora page-break
controls.

Run the PDF stage and validation independently when needed:

```powershell
.\.venv\Scripts\python.exe scripts\build_pdfs.py
.\.venv\Scripts\python.exe scripts\validate_pdfs.py
```

See [the PDF generation guide](docs/pdf_generation.md) for typography,
licensing, caching, validation, and visual-QA details.

## GitHub Pages deployment

The generated application is fully static. It uses artifact-relative URLs, so
the same output works at a repository subpath such as
`https://<account>.github.io/blue-sora/` and at a custom domain. No Python
process, API, or database runs after deployment.

Regenerate and validate the versioned Pages artifact before committing it:

```powershell
.\.venv\Scripts\python.exe scripts\build_site.py
.\.venv\Scripts\python.exe scripts\validate_site.py
```

Then enable **Settings → Pages → Source: GitHub Actions**. The included workflow
validates and uploads `build/site` whenever that artifact changes. See
[the deployment guide](docs/github_pages.md).
