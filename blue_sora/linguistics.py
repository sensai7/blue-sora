"""Japanese prose metrics and the versioned Blue Sora difficulty model."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any, Iterable

from fugashi import Tagger


MODEL_VERSION = "blue-sora-difficulty-v1"
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])|\n+")
KANJI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヶ]")
EXCLUDED_POS = {"補助記号", "空白", "記号"}


_TAGGER: Tagger | None = None


def tagger() -> Tagger:
    global _TAGGER
    if _TAGGER is None:
        _TAGGER = Tagger()
    return _TAGGER


def inline_text(nodes: Iterable[dict[str, Any]]) -> str:
    parts: list[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "text":
            parts.append(node.get("text", ""))
        elif node_type == "ruby":
            parts.append(inline_text(node.get("base", [])))
        elif node_type == "line_break":
            parts.append("\n")
        elif node_type == "note":
            continue
        elif node_type in {
            "anchor", "emphasis", "small", "source_markup", "styled",
            "subscript", "superscript", "warichu",
        }:
            parts.append(inline_text(node.get("children", [])))
    return "".join(parts)


def prose_text(blocks: Iterable[dict[str, Any]]) -> str:
    """Extract readable prose while excluding headings and editorial notes."""
    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "paragraph":
            parts.append(inline_text(block.get("inlines", [])))
        elif block_type == "styled_block":
            parts.append(prose_text(block.get("blocks", [])))
        elif block_type == "list":
            for item in block.get("items", []):
                parts.append(prose_text(item))
            parts.append(prose_text(block.get("supplemental", [])))
        elif block_type == "table":
            for row in block.get("rows", []):
                for cell in row:
                    parts.append(prose_text(cell))
    return "\n".join(part for part in parts if part)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_BOUNDARY_RE.split(text) if part.strip()]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in tagger()(text):
        surface = word.surface.strip()
        if not surface or word.feature.pos1 in EXCLUDED_POS:
            continue
        lemma = getattr(word.feature, "lemma", None)
        tokens.append(lemma if lemma and lemma != "*" else surface)
    return tokens


@dataclass
class WorkBase:
    work_id: str
    source_sha256: str
    characters: int
    sentences: int
    sentence_word_counts: list[int]
    words: Counter[str]
    kanji: Counter[str]


def analyze_base(document: dict[str, Any]) -> WorkBase:
    text = prose_text(document["content"]["body"])
    sentences = split_sentences(text)
    word_counter = Counter(tokenize(text))
    return WorkBase(
        work_id=str(document["metadata"]["作品ID"]).zfill(6),
        source_sha256=document["provenance"]["source_sha256"],
        characters=sum(not character.isspace() for character in text),
        sentences=len(sentences),
        sentence_word_counts=[len(tokenize(sentence)) for sentence in sentences],
        words=word_counter,
        kanji=Counter(KANJI_RE.findall(text)),
    )


def average_surprisal(counter: Counter[str], corpus: Counter[str]) -> float | None:
    observations = sum(counter.values())
    total = sum(corpus.values())
    vocabulary = len(corpus)
    if not observations or not total:
        return None
    return sum(
        count * -math.log10((corpus[item] + 1) / (total + vocabulary))
        for item, count in counter.items()
    ) / observations


def scaled(value: float | None, floor: float, ceiling: float) -> float | None:
    if value is None:
        return None
    return max(0.0, min(100.0, (value - floor) / (ceiling - floor) * 100.0))


def finalize(
    base: WorkBase,
    corpus_words: Counter[str],
    corpus_kanji: Counter[str],
) -> dict[str, Any]:
    length_words = sum(base.words.values())
    unique_words = len(base.words)
    hapax_words = sum(count == 1 for count in base.words.values())
    unique_kanji = len(base.kanji)
    hapax_kanji = sum(count == 1 for count in base.kanji.values())
    average_sentence_length = (
        sum(base.sentence_word_counts) / len(base.sentence_word_counts)
        if base.sentence_word_counts else None
    )
    lexical_surprisal = average_surprisal(base.words, corpus_words)
    kanji_surprisal = average_surprisal(base.kanji, corpus_kanji)
    components = {
        "lexical_rarity": scaled(lexical_surprisal, 2.0, 5.0),
        "kanji_rarity": scaled(kanji_surprisal, 1.5, 4.0),
        "sentence_complexity": scaled(average_sentence_length, 5.0, 40.0),
    }

    diagnostics: list[dict[str, str]] = []
    status = "ok"
    if length_words == 0 or not base.sentence_word_counts:
        status = "failed"
        diagnostics.append({"severity": "error", "code": "insufficient_prose"})
    elif length_words < 100:
        status = "outlier"
        diagnostics.append({"severity": "warning", "code": "too_short_for_score"})
    elif base.sentences < 2:
        status = "outlier"
        diagnostics.append({"severity": "warning", "code": "insufficient_sentence_boundaries"})
    elif average_sentence_length is not None and average_sentence_length > 100:
        status = "outlier"
        diagnostics.append({"severity": "warning", "code": "extreme_sentence_length"})

    score = None
    if status == "ok" and all(value is not None for value in components.values()):
        score = round(
            components["lexical_rarity"] * 0.55
            + components["kanji_rarity"] * 0.25
            + components["sentence_complexity"] * 0.20,
            2,
        )

    return {
        "work_id": base.work_id,
        "model_version": MODEL_VERSION,
        "status": status,
        "metrics": {
            "length_words": length_words,
            "unique_words": unique_words,
            "hapax_words": hapax_words,
            "hapax_words_percent": round(hapax_words / unique_words * 100, 2) if unique_words else None,
            "unique_kanji": unique_kanji,
            "hapax_kanji": hapax_kanji,
            "average_sentence_length": round(average_sentence_length, 2) if average_sentence_length is not None else None,
            "characters": base.characters,
            "sentences": base.sentences,
        },
        "difficulty": {
            "average_difficulty": score,
            "components": {key: round(value, 2) if value is not None else None for key, value in components.items()},
            "raw": {
                "average_lexical_surprisal": round(lexical_surprisal, 6) if lexical_surprisal is not None else None,
                "average_kanji_surprisal": round(kanji_surprisal, 6) if kanji_surprisal is not None else None,
            },
            "weights": {"lexical_rarity": 0.55, "kanji_rarity": 0.25, "sentence_complexity": 0.20},
        },
        "diagnostics": diagnostics,
        "provenance": {
            "source_sha256": base.source_sha256,
            "tokenizer": "fugashi+unidic-lite",
            "fugashi_version": version("fugashi"),
            "unidic_lite_version": version("unidic-lite"),
        },
    }


def corpus_fingerprint(bases: Iterable[WorkBase]) -> str:
    joined = "\n".join(f"{base.work_id}:{base.source_sha256}" for base in sorted(bases, key=lambda item: item.work_id))
    return hashlib.sha256(joined.encode("ascii")).hexdigest()
