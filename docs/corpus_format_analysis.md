# Reduced corpus format analysis

## Dataset

The reduced corpus contains 126 HTML works and 126 matching metadata rows:

- 江戸川乱歩: 55
- 福沢諭吉: 35
- 樋口一葉: 36
- 樋口夏子: 0 under that name; the supplied CSV catalogues her works as
  樋口一葉

All 126 selected metadata records have a corresponding corpus file. The
original corpus already excludes the short works mentioned in the project
brief; no selected files are missing.

## Encoding and outer structure

- `aozora.csv` is UTF-8 with a BOM, despite the work files being Shift-JIS.
- All 126 selected HTML files declare `shift_jis` and decode cleanly with
  Python's `cp932` codec. CP932 is an appropriate tolerant decoder for this
  historical Shift-JIS material.
- All 126 declare XHTML 1.1.
- All 126 contain `div.main_text` and Dublin Core `DC.Creator` metadata.
- The source files should remain immutable. Decode during ingestion, normalize
  to Unicode internally, and emit generated pages as UTF-8.

## Structural variation

The common shell is reliable, but content markup is not uniform enough to copy
directly into the generated site.

- Every document has an `h1`, normally the work title. `h2`-`h5` usage varies.
- Chapter/section labels use Aozora classes rather than one fixed element:
  `o-midashi`, `naka-midashi`, `ko-midashi`, `mado-naka-midashi`,
  `dogyo-naka-midashi`, and `dogyo-ko-midashi`.
- `midashi_anchor` is commonly attached to a heading anchor and is not itself a
  semantic heading level.
- Ruby is pervasive: 123 of 126 files contain ruby markup, with 64,361 ruby
  elements in the reduced set.
- 45 files contain images. Relative image URLs cannot be assumed to resolve in
  a separately generated site.
- Presentational classes include indentation (`jisage_*`), right alignment
  (`chitsuki_*`), emphasis (`sesame_dot`, `futoji`), boxed text (`keigakomi`),
  annotations (`notes`, `warichu`), gaiji, and illustrations.
- Bibliographic and notation-note sections follow the main text and must not be
  counted as prose or placed inside the reader body.

## Baseline size and outlier signals

For the current parser's visible text extraction:

| Measure | Minimum | Median | Mean | Maximum |
|---|---:|---:|---:|---:|
| Visible characters | 1,056 | 12,293 | 28,314 | 278,818 |
| File bytes | 5,093 | 40,720 | 88,090 | 1,317,714 |
| Sentences | 1 | 132 | 595 | 3,828 |
| Unique kanji | 28 | 612 | 694 | 2,384 |

There are no files below 1,000 visible characters, no files without a detected
sentence, and no decoding replacements. Very low sentence counts should still
be reviewed: punctuation conventions and headings can make sentence-based
metrics misleading even when a file is valid.

## Proposed canonical work format

The ingestion layer should produce a UTF-8, source-independent work model. A
practical first schema is:

```text
Work
  metadata: id, title, subtitle, author(s), dates, source URLs, source edition
  blocks[]:
    heading(level=2..4, text, anchor)
    paragraph(inlines[])
    image(asset, alt, caption)
    separator
    note(text)
  bibliographic_information
  notation_notes
```

Normalization rules:

1. Extract only `div.main_text` as readable prose. Store bibliography and
   notation notes separately.
2. Map `o-midashi` to `h2`, `naka-midashi` and its window/inline variants to
   `h3`, and `ko-midashi` variants to `h4`. Clamp any ambiguous source heading
   to this hierarchy while preserving its source class for diagnostics.
3. Preserve ruby semantically as `<ruby><rb>…</rb><rt>…</rt></ruby>`; remove
   fallback `rp` parentheses in modern HTML output.
4. Convert layout-only indentation and alignment classes into a small,
   documented set of semantic block styles. Do not carry numbered `jisage_*`
   classes into the public template.
5. Preserve emphasis, gaiji fallbacks, notes, and warichu explicitly. Log any
   unrecognized tag/class rather than silently discarding it.
6. Resolve images during ingestion, copy them to generated assets, and record
   missing assets as validation errors.
7. Keep provenance for every normalized work: source filename, decoder,
   parser version, warnings, and a hash of the source bytes.
8. Calculate linguistic statistics from normalized prose, excluding headings,
   ruby readings, bibliography, and editorial notes.

This intermediate model should be the single input for HTML, EPUB, and PDF.
Maintaining three separate parsers would cause the output formats to drift.
