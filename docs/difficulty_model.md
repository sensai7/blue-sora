# Linguistic metrics and difficulty model

Milestone 3 uses fugashi 1.5.2 with unidic-lite 1.0.8. The model identifier is
`blue-sora-difficulty-v1`; dependency versions and source hashes are retained in
every result.

## Prose selection

Metrics use paragraphs in the canonical `body` section. Headings,
bibliography, notation notes, editorial `note` nodes, image alternatives, and
ruby readings are excluded. Ruby base text, authorial warichu, and emphasis
remain part of the prose.

## Definitions

- **Length (words):** UniDic tokens excluding whitespace, punctuation, and
  symbols. Lemmas are used when UniDic supplies one; otherwise surface forms.
- **Unique words:** distinct normalized lemmas within the work.
- **Unique words used once:** lemmas occurring exactly once in the work.
- **Unique words used once %:** single-use lemmas divided by unique lemmas.
- **Unique kanji:** distinct CJK ideographs, including iteration mark `々`.
- **Unique kanji used once:** kanji occurring exactly once in the work.
- **Average sentence length:** word tokens per non-empty sentence.
- **Characters:** non-whitespace prose characters.
- **Sentence boundaries:** `。`, `！`, `？`, `!`, `?`, or a canonical prose
  line/paragraph break. The latter is required for older works whose source
  typography separates sentences without modern punctuation.

## Difficulty v1

The corpus itself supplies reproducible frequency data. Token and kanji rarity
are mean add-one-smoothed base-10 surprisal values. Three 0–100 components are
retained alongside the raw values:

```text
average_difficulty =
  lexical_rarity      × 0.55 +
  kanji_rarity        × 0.25 +
  sentence_complexity × 0.20
```

Fixed scaling ranges are lexical surprisal 2–5, kanji surprisal 1.5–4, and
average sentence length 5–40 words. Values are clamped to 0–100. This keeps the
formula inspectable and prevents a corpus outlier from silently rescaling all
other works.

Works with no analyzable prose, fewer than 100 tokens, fewer than two detected
sentences, or more than 100 words per sentence are reported as failed/outlier
and receive a null score. Raw metrics and diagnostics remain available.
