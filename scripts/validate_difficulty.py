"""Validate Milestone 3 linguistic-analysis artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blue_sora.linguistics import MODEL_VERSION


REQUIRED_METRICS = {
    "length_words", "unique_words", "hapax_words", "hapax_words_percent",
    "unique_kanji", "hapax_kanji", "average_sentence_length", "characters",
    "sentences",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=Path("build/canonical"))
    parser.add_argument("--analysis", type=Path, default=Path("build/analysis"))
    parser.add_argument("--expected-works", type=int, default=126)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    canonical_ids = {path.stem for path in args.canonical.glob("*.json")}
    analysis_paths = sorted(path for path in args.analysis.glob("*.json") if path.name != "summary.json")
    analysis_ids = {path.stem for path in analysis_paths}
    if len(analysis_paths) != args.expected_works or canonical_ids != analysis_ids:
        raise SystemExit("Canonical/analysis document sets do not match")

    statuses: dict[str, int] = {"ok": 0, "outlier": 0, "failed": 0}
    for path in analysis_paths:
        item = json.loads(path.read_text(encoding="utf-8"))
        if item["model_version"] != MODEL_VERSION:
            raise SystemExit(f"{path.name}: unexpected model version")
        if set(item["metrics"]) != REQUIRED_METRICS:
            raise SystemExit(f"{path.name}: incomplete metric set")
        status = item["status"]
        statuses[status] = statuses.get(status, 0) + 1
        score = item["difficulty"]["average_difficulty"]
        if status == "ok" and (score is None or not 0 <= score <= 100):
            raise SystemExit(f"{path.name}: valid work lacks a bounded score")
        if status != "ok" and (score is not None or not item["diagnostics"]):
            raise SystemExit(f"{path.name}: abnormal work has a misleading score or no diagnostic")
        if not item["provenance"].get("source_sha256"):
            raise SystemExit(f"{path.name}: missing source provenance")

    summary = json.loads((args.analysis / "summary.json").read_text(encoding="utf-8"))
    if summary["model_version"] != MODEL_VERSION or summary["works"] != len(analysis_paths):
        raise SystemExit("Analysis summary does not match artifacts")
    print(f"Analysis documents: {len(analysis_paths)}")
    print(f"Scored works:       {statuses['ok']}")
    print(f"Reported outliers:  {statuses['outlier']}")
    print(f"Failed analyses:    {statuses['failed']}")
    print(f"Model version:      {MODEL_VERSION}")


if __name__ == "__main__":
    main()
