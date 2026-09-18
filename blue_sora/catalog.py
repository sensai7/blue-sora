"""Validated, deterministic catalog artifact construction."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


GENERATOR_VERSION = "blue-sora-catalog-v1"
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas" / "catalog"


def normalized_id(value: str) -> str:
    return str(value).zfill(6)


def work_id(value: str) -> str:
    return f"aozora:work:{normalized_id(value)}"


def work_slug(value: str) -> str:
    return f"aozora-{normalized_id(value)}"


def person_id(value: str) -> str:
    return f"aozora:person:{normalized_id(value)}"


def person_slug(value: str) -> str:
    return f"aozora-person-{normalized_id(value)}"


def optional(value: Any) -> Any:
    return value if value not in {None, ""} else None


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def input_fingerprint(canonical_bytes: bytes, analysis_bytes: bytes) -> str:
    return sha256_bytes(GENERATOR_VERSION.encode("ascii") + b"\0" + canonical_bytes + b"\0" + analysis_bytes)


def build_author(metadata: dict[str, str], works: Iterable[str]) -> dict[str, Any]:
    raw_id = normalized_id(metadata["人物ID"])
    family = metadata.get("姓", "")
    given = metadata.get("名", "")
    family_reading = metadata.get("姓読み", "")
    given_reading = metadata.get("名読み", "")
    romanized = " ".join(filter(None, [metadata.get("名ローマ字", ""), metadata.get("姓ローマ字", "")]))
    return {
        "schema_version": 1,
        "id": person_id(raw_id),
        "aozora_person_id": raw_id,
        "slug": person_slug(raw_id),
        "name": {
            "display": family + given,
            "family": family,
            "given": given,
            "reading": family_reading + given_reading,
            "romanized": romanized,
        },
        "birth_date": optional(metadata.get("生年月日")),
        "death_date": optional(metadata.get("没年月日")),
        "copyright": optional(metadata.get("人物著作権フラグ")),
        "work_ids": sorted(set(works)),
    }


def edition(metadata: dict[str, str], number: int = 1) -> dict[str, Any]:
    suffix = str(number)
    return {
        "name": optional(metadata.get(f"底本名{suffix}")),
        "publisher": optional(metadata.get(f"底本出版社名{suffix}")),
        "first_publication": optional(metadata.get(f"底本初版発行年{suffix}")),
        "input_edition": optional(metadata.get(f"入力に使用した版{suffix}")),
        "proof_edition": optional(metadata.get(f"校正に使用した版{suffix}")),
    }


def build_work(canonical: dict[str, Any], analysis: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    metadata = canonical["metadata"]
    raw_work_id = normalized_id(metadata["作品ID"])
    raw_person_id = normalized_id(metadata["人物ID"])
    assets = [
        {
            **asset,
            "build_path": f"canonical/{asset['local_path']}",
        }
        for asset in canonical["assets"]
    ]
    for asset in assets:
        asset.pop("local_path", None)
    return {
        "schema_version": 1,
        "id": work_id(raw_work_id),
        "aozora_work_id": raw_work_id,
        "slug": work_slug(raw_work_id),
        "title": {
            "display": metadata["作品名"],
            "reading": optional(metadata.get("作品名読み")),
            "subtitle": optional(metadata.get("副題")),
        },
        "author_ids": [person_id(raw_person_id)],
        "first_publication": optional(metadata.get("初出")),
        "orthography": optional(metadata.get("文字遣い種別")),
        "published_at": optional(metadata.get("公開日")),
        "edition": edition(metadata),
        "assets": assets,
        "analytics": {key: value for key, value in analysis.items() if key != "work_id"},
        "diagnostics": [
            {"source": "ingestion", "items": canonical["warnings"]},
            {"source": "analysis", "items": analysis["diagnostics"]},
        ],
        "content": canonical["content"],
        "source": {
            "card_url": optional(metadata.get("図書カードURL")),
            "xhtml_url": optional(metadata.get("XHTML/HTMLファイルURL")),
            "metadata": metadata,
            "provenance": canonical["provenance"],
        },
        "reproducibility": {"input_sha256": fingerprint, "generator_version": GENERATOR_VERSION},
    }


def catalog_entry(work: dict[str, Any], authors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    author_summaries = [
        {"id": author_id, "name": authors[author_id]["name"]["display"], "romanized": authors[author_id]["name"]["romanized"]}
        for author_id in work["author_ids"]
    ]
    return {
        "id": work["id"],
        "slug": work["slug"],
        "title": work["title"]["display"],
        "title_reading": work["title"]["reading"],
        "subtitle": work["title"]["subtitle"],
        "authors": author_summaries,
        "published_at": work["published_at"],
        "orthography": work["orthography"],
        "metrics": work["analytics"]["metrics"],
        "difficulty": {
            "status": work["analytics"]["status"],
            **work["analytics"]["difficulty"],
        },
        "asset_count": len(work["assets"]),
        "has_illustrations": any(asset["kind"] == "illustration" for asset in work["assets"]),
    }


def search_entry(entry: dict[str, Any]) -> dict[str, Any]:
    fields = [entry["title"], entry.get("title_reading") or ""]
    for author in entry["authors"]:
        fields.extend([author["name"], author["romanized"]])
    return {"id": entry["id"], "slug": entry["slug"], "text": " ".join(filter(None, fields)).casefold()}


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate_schema(instance: Any, schema_name: str) -> None:
    errors = sorted(Draft202012Validator(load_schema(schema_name)).iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = "/".join(str(item) for item in error.absolute_path) or "<root>"
        raise ValueError(f"{schema_name} validation failed at {location}: {error.message}")


def validate_relations(works: Iterable[dict[str, Any]], authors: dict[str, dict[str, Any]]) -> None:
    work_list = list(works)
    work_ids = {work["id"] for work in work_list}
    if len(work_ids) != len(work_list):
        raise ValueError("Duplicate work IDs")
    slugs = [work["slug"] for work in work_list]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate work slugs")
    for work in work_list:
        missing = set(work["author_ids"]) - set(authors)
        if missing:
            raise ValueError(f"{work['id']} references missing authors: {sorted(missing)}")
    for author in authors.values():
        missing = set(author["work_ids"]) - work_ids
        if missing:
            raise ValueError(f"{author['id']} references missing works: {sorted(missing)}")


def write_if_changed(path: Path, value: Any) -> tuple[str, bool]:
    payload = canonical_json(value)
    checksum = sha256_bytes(payload)
    if path.is_file() and path.read_bytes() == payload:
        return checksum, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return checksum, True
