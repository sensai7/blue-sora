# Reduced corpus format analysis

## Dataset

The reduced corpus contains 1,061 HTML works and 1,061 matching metadata rows
from 14 author records:

- 芥川竜之介: 371; 太宰治: 272; 夏目漱石: 104; 森鴎外: 89
- 江戸川乱歩: 55; 樋口一葉: 36; 福沢諭吉: 35; 田山花袋: 28
- 谷崎潤一郎: 23; 徳田秋声: 21; 二葉亭四迷: 11; 上田敏: 7
- 小泉八雲: 5; 坪内逍遥: 4

All selected metadata records have a corresponding corpus file. `樋口夏子` is
included in the selector for compatibility, but the supplied CSV catalogues
those works under the pen name `樋口一葉`; Akutagawa is catalogued as
`芥川竜之介`.

## Encoding and outer structure

- `aozora.csv` is UTF-8 with a BOM, despite the work files being Shift-JIS.
- The selected HTML files declare `shift_jis`. Ingestion uses Python's `cp932`
  codec with replacement handling so isolated invalid bytes in publisher notes
  cannot discard an otherwise readable work.
- The corpus uses XHTML 1.1 with `div.main_text` and Dublin Core `DC.Creator`
  metadata; individual works still vary in their inline and presentational
  markup.
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
- Ruby is pervasive, and illustrations and gaiji occur throughout the corpus.
  Relative image URLs cannot be assumed to resolve in a separately generated
  site.
- Presentational classes include indentation (`jisage_*`), right alignment
  (`chitsuki_*`), emphasis (`sesame_dot`, `futoji`), boxed text (`keigakomi`),
  annotations (`notes`, `warichu`), gaiji, and illustrations.
- Bibliographic and notation-note sections follow the main text and must not be
  counted as prose or placed inside the reader body.

## Baseline and outlier signals

The expanded corpus deliberately contains a wider range of forms and lengths
than the original 126-work development set. Rebuild `build/analysis` and use
`scripts/validate_difficulty.py` to obtain current aggregate figures; do not
treat legacy sample statistics as corpus-wide limits. Very low sentence counts
and decoding replacements are diagnostics to review, not automatic grounds to
discard a work.

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
