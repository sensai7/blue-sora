"""Generate versioned Japanese-learning metrics for canonical works."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.linguistics import MODEL_VERSION, analyze_base, corpus_fingerprint, finalize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=Path("build/canonical"))
    parser.add_argument("--output", type=Path, default=Path("build/analysis"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = sorted(args.canonical.glob("*.json"))
    if not paths:
        raise SystemExit(f"No canonical JSON files found in {args.canonical}")
    bases = [analyze_base(json.loads(path.read_text(encoding="utf-8"))) for path in paths]
    corpus_words: Counter[str] = Counter()
    corpus_kanji: Counter[str] = Counter()
    for base in bases:
        corpus_words.update(base.words)
        corpus_kanji.update(base.kanji)

    args.output.mkdir(parents=True, exist_ok=True)
    analyses = [finalize(base, corpus_words, corpus_kanji) for base in bases]
    for analysis in analyses:
        (args.output / f"{analysis['work_id']}.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    outliers = [
        {"work_id": item["work_id"], "status": item["status"], "diagnostics": item["diagnostics"]}
        for item in analyses if item["status"] != "ok"
    ]
    summary = {
        "model_version": MODEL_VERSION,
        "corpus_fingerprint": corpus_fingerprint(bases),
        "works": len(analyses),
        "total_words": sum(corpus_words.values()),
        "vocabulary_words": len(corpus_words),
        "unique_kanji": len(corpus_kanji),
        "scored_works": sum(item["status"] == "ok" for item in analyses),
        "outliers": outliers,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Analyzed works: {len(analyses)}")
    print(f"Scored works:   {summary['scored_works']}")
    print(f"Outliers:       {len(outliers)}")
    print(f"Corpus words:   {summary['total_words']:,}")
    print(f"Vocabulary:     {summary['vocabulary_words']:,}")


if __name__ == "__main__":
    main()
