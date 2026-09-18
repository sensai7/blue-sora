# Blue Sora roadmap

## 1. Corpus foundation and audit

Create a reproducible development subset, preserve source encodings, establish
baseline quality metrics, and document real HTML variation.

## 2. Canonical Aozora ingestion

Implement a tested Shift-JIS-to-Unicode parser that separates metadata, prose,
bibliography, notes, headings, ruby, images, and unusual inline markup into one
canonical work model.

## 3. Linguistic analysis and difficulty model

Add Japanese morphological tokenization and calculate word, character, kanji,
sentence, frequency, and difficulty features with documented definitions and a
versioned scoring model.

## 4. Catalog data model and build artifacts

Combine normalized works, metadata, diagnostics, and analytics into validated,
cacheable JSON artifacts suitable for static-site generation and searching.

## 5. Static site generator and design system

Create the HTML/CSS/JS generation pipeline, responsive layout, typography,
navigation, accessibility baseline, and black cover placeholder component.

## 6. Library browsing, search, and filters

Build an attractive English-facing catalog with author/title search, sorting,
pagination, and filters for length, difficulty, era, and other available data.

## 7. Work page and online reader

Generate each work page with cover, essential metadata, the complete difficulty
panel, export buttons, and a readable, navigable “Read here” section.

## 8. EPUB generation

Generate standards-compliant EPUB files from the canonical model, including
metadata, navigation, ruby, chapters, images, and embedded reading styles.

## 9. PDF generation

Generate print-ready PDFs with Japanese font embedding, correct line breaking,
ruby handling, chapters, metadata, and stable downloadable output.

## 10. Full-corpus validation and release

Run the complete corpus through the pipeline, triage parser exceptions and
outliers, add automated regression/accessibility checks, optimize output, and
document repeatable builds and deployment.
