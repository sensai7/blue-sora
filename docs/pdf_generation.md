# PDF generation

Milestone 9 produces one deterministic, print-ready A5 PDF per reduced-corpus
work at `build/site/downloads/<stable-slug>.pdf`. The site build generates PDFs
before rendering work pages, so a PDF button is enabled only when its local
artifact exists.

## Rendering pipeline

The renderer uses ReportLab 4.4.9 and a vendored BIZ UD Mincho Regular font.
BIZ UD Mincho is maintained by the BIZ UDMincho Project Authors and distributed
under the SIL Open Font License 1.1; the original font and license are retained
under `assets/fonts/biz-ud-mincho/`.

The output includes:

- embedded, subsetted Japanese font data and Unicode character maps;
- selectable and searchable Japanese prose;
- CJK line wrapping with ReportLab's Japanese kinsoku handling;
- true ruby layout with smaller readings centered above each complete base word;
- source illustrations and gaiji, without remote assets;
- source heading hierarchy and PDF outline bookmarks;
- explicit handling of Aozora page-break instructions;
- A5 margins, running headers, page numbers, and controlled heading breaks;
- PDF title, author, subject/source, and generator metadata; and
- final source attribution and font-license notes.

ReportLab's invariant output mode, a fixed font asset, stable input
fingerprints, and a versioned generator make output reproducible. An unchanged
full build does not rewrite any PDF.

## Validation

Run:

```powershell
.\.venv\Scripts\python.exe scripts\validate_pdfs.py
```

Every PDF is reopened with pypdf. Validation checks page structure, title
metadata, searchable text, replacement glyphs, embedded font files, Unicode
coverage of canonical source characters, source attribution, and canonical
images. The validator reports explicit short, long, illustrated, and
ruby-heavy representatives.

Visual QA uses Poppler to render representative cover, prose, heading,
illustration/table, long-work middle, and colophon pages to PNG. Those rendered
pages are inspected for clipping, overlap, missing glyphs, line-breaking,
margin consistency, and header/footer placement.
