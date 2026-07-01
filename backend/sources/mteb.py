from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Sequence

import httpx

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, compact_text, percent_score, safe_float, utc_now_iso


PATHS_URL = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/paths.json"
RAW_RESULTS_BASE_URL = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/"
MAX_MODELS = 80
MAX_TASK_FILES_PER_MODEL = 12
MAX_TOTAL_TASK_FILES = 500
RETRIEVAL_TASK_NAMES = {
    "arguana",
    "climatefever",
    "cqadupstackandroidretrieval",
    "cqadupstackenglishretrieval",
    "cqadupstackgamingretrieval",
    "cqadupstackgisretrieval",
    "cqadupstackmathematica",
    "cqadupstackphysics",
    "cqadupstackprogrammersretrieval",
    "cqadupstackstatsretrieval",
    "cqadupstacktexretrieval",
    "cqadupstackunixretrieval",
    "cqadupstackwebmastersretrieval",
    "cqadupstackwordpressretrieval",
    "dbpedia",
    "fever",
    "fiqa2018",
    "hotpotqa",
    "msmarco",
    "nfcorpus",
    "nq",
    "quoraretrieval",
    "scidocs",
    "touche2020",
    "treccovid",
}


class MtebAdapter(BaseSourceAdapter):
    source_id = "mteb"
    benchmark_ids = ("mteb_retrieval", "mteb_reranking", "mteb_retrieval_reranking")
    source_url = "https://github.com/embeddings-benchmark/results"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        fetched_at = utc_now_iso()
        response = await client.get(PATHS_URL, timeout=30.0)
        response.raise_for_status()
        paths_payload = response.json()
        if not isinstance(paths_payload, dict):
            raise ValueError("MTEB paths payload was not a JSON object.")

        raw_records: list[RawSourceRecord] = []
        total_task_files = 0
        for model_dir, raw_paths in list(paths_payload.items())[:MAX_MODELS]:
            if not isinstance(raw_paths, list):
                continue
            selected_paths = _selected_task_paths(raw_paths)
            if not selected_paths:
                continue

            for result_path in selected_paths[:MAX_TASK_FILES_PER_MODEL]:
                if total_task_files >= MAX_TOTAL_TASK_FILES:
                    break
                record = await _fetch_result_record(client, model_dir, str(result_path), fetched_at)
                if record is not None:
                    raw_records.append(record)
                    total_task_files += 1
            if total_task_files >= MAX_TOTAL_TASK_FILES:
                break

        if not raw_records:
            raise ValueError("Could not parse any MTEB retrieval or reranking result rows.")
        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        grouped: dict[tuple[str, str], list[RawSourceRecord]] = defaultdict(list)
        for record in raw_records:
            category = compact_text(record.metadata.get("task_category"))
            if category not in {"retrieval", "reranking"}:
                continue
            grouped[(record.raw_model_key or record.raw_model_name, category)].append(record)

        candidates: list[ScoreCandidate] = []
        category_records_by_model: dict[str, dict[str, list[RawSourceRecord]]] = defaultdict(dict)
        for (model_key, category), records in grouped.items():
            category_records_by_model[model_key][category] = records
            candidate = _category_candidate(model_key, category, records)
            if candidate is not None:
                candidates.append(candidate)

        for model_key, categories in category_records_by_model.items():
            if "retrieval" not in categories or "reranking" not in categories:
                continue
            combined_records = [*categories["retrieval"], *categories["reranking"]]
            candidate = _combined_candidate(model_key, combined_records)
            if candidate is not None:
                candidates.append(candidate)

        return candidates


async def _fetch_result_record(
    client: httpx.AsyncClient,
    model_dir: str,
    result_path: str,
    fetched_at: str,
) -> RawSourceRecord | None:
    task_name = _task_name_from_path(result_path)
    category = _task_category(task_name)
    if category is None:
        return None

    source_url = f"{RAW_RESULTS_BASE_URL}{result_path}"
    try:
        response = await client.get(source_url, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPStatusError:
        return None
    payload = response.json()
    if not isinstance(payload, dict):
        return None

    score_entries = list(_score_entries(payload.get("scores")))
    main_scores = [percent_score(entry.get("main_score")) for entry in score_entries if isinstance(entry, dict)]
    main_scores = [score for score in main_scores if score is not None]
    if not main_scores:
        return None

    value = round(sum(main_scores) / len(main_scores), 4)
    model_name = _model_name_from_dir(model_dir)
    revision = _revision_from_path(result_path)
    languages = sorted(
        {
            language
            for entry in score_entries
            if isinstance(entry, dict)
            for language in _language_entries(entry.get("languages"))
        }
    )

    metadata = {
        "model_provider": model_name.split("/", 1)[0] if "/" in model_name else None,
        "model_roles": ["embedding"] if category == "retrieval" else ["reranker"],
        "task_category": category,
        "task_name": compact_text(payload.get("task_name")) or task_name,
        "task_path": result_path,
        "revision": revision,
        "mteb_version": compact_text(payload.get("mteb_version")) or None,
        "dataset_revision": compact_text(payload.get("dataset_revision")) or None,
        "languages": languages,
        "split_count": len(score_entries),
        "score_count": len(main_scores),
        "source_policy": "official_results_repo_task_main_score_average",
    }
    return RawSourceRecord(
        source_id="mteb",
        benchmark_id=f"mteb_{category}",
        raw_model_name=model_name,
        raw_model_key=model_name,
        raw_value=_format_score(value),
        source_url=source_url,
        collected_at=fetched_at,
        payload=payload,
        metadata=metadata,
    )


def _selected_task_paths(paths: Iterable[Any]) -> list[str]:
    selected_by_task: dict[tuple[str, str], str] = {}
    for raw_path in paths:
        result_path = compact_text(raw_path)
        if not result_path.endswith(".json"):
            continue
        task_name = _task_name_from_path(result_path)
        category = _task_category(task_name)
        if category is None:
            continue
        selected_by_task.setdefault((category, task_name.casefold()), result_path)

    by_category: dict[str, list[str]] = {"retrieval": [], "reranking": []}
    for result_path in selected_by_task.values():
        category = _task_category(_task_name_from_path(result_path))
        if category in by_category:
            by_category[category].append(result_path)

    for category_paths in by_category.values():
        category_paths.sort(key=lambda path: (_task_name_from_path(path).casefold(), path))

    balanced: list[str] = []
    for index in range(max(len(by_category["retrieval"]), len(by_category["reranking"]))):
        for category in ("retrieval", "reranking"):
            if index < len(by_category[category]):
                balanced.append(by_category[category][index])
    return balanced


def _category_candidate(model_key: str, category: str, records: list[RawSourceRecord]) -> ScoreCandidate | None:
    scores = [safe_float(record.raw_value) for record in records]
    scores = [score for score in scores if score is not None]
    if not scores:
        return None

    value = round(sum(scores) / len(scores), 4)
    first_record = records[0]
    benchmark_id = f"mteb_{category}"
    role = "embedding" if category == "retrieval" else "reranker"
    task_names = sorted({compact_text(record.metadata.get("task_name")) for record in records if record.metadata.get("task_name")})
    languages = sorted(
        {
            language
            for record in records
            for language in _language_entries(record.metadata.get("languages"))
        }
    )
    return ScoreCandidate(
        source_id="mteb",
        benchmark_id=benchmark_id,
        raw_model_name=first_record.raw_model_name,
        raw_model_key=model_key,
        value=value,
        raw_value=_format_score(value),
        source_url=MtebAdapter.source_url,
        collected_at=first_record.collected_at,
        source_type="primary",
        verified=True,
        notes=f"Official MTEB {category} main-score average across {len(scores)} task result file(s).",
        metadata={
            "model_provider": first_record.metadata.get("model_provider"),
            "model_roles": [role],
            "task_category": category,
            "task_names": task_names,
            "languages": languages,
            "score_count": len(scores),
            "source_policy": "official_results_repo_category_main_score_average",
        },
    )


def _combined_candidate(model_key: str, records: list[RawSourceRecord]) -> ScoreCandidate | None:
    scores = [safe_float(record.raw_value) for record in records]
    scores = [score for score in scores if score is not None]
    if not scores:
        return None

    value = round(sum(scores) / len(scores), 4)
    first_record = records[0]
    task_categories = sorted({compact_text(record.metadata.get("task_category")) for record in records})
    return ScoreCandidate(
        source_id="mteb",
        benchmark_id="mteb_retrieval_reranking",
        raw_model_name=first_record.raw_model_name,
        raw_model_key=model_key,
        value=value,
        raw_value=_format_score(value),
        source_url=MtebAdapter.source_url,
        collected_at=first_record.collected_at,
        source_type="primary",
        verified=True,
        notes=f"Official MTEB blended retrieval/reranking main-score average across {len(scores)} task result file(s).",
        metadata={
            "model_provider": first_record.metadata.get("model_provider"),
            "model_roles": ["embedding", "reranker"],
            "task_categories": task_categories,
            "score_count": len(scores),
            "source_policy": "official_results_repo_retrieval_reranking_average",
        },
    )


def _score_entries(scores_payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(scores_payload, dict):
        for split_entries in scores_payload.values():
            if isinstance(split_entries, list):
                for entry in split_entries:
                    if isinstance(entry, dict):
                        yield entry
            elif isinstance(split_entries, dict):
                yield split_entries


def _language_entries(value: Any) -> list[str]:
    if isinstance(value, list):
        return [compact_text(item) for item in value if compact_text(item)]
    text = compact_text(value)
    return [text] if text else []


def _task_category(task_name: str) -> str | None:
    lowered = task_name.casefold()
    if "reranking" in lowered or "rerank" in lowered:
        return "reranking"
    if "retrieval" in lowered or lowered in RETRIEVAL_TASK_NAMES:
        return "retrieval"
    return None


def _task_name_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".json")


def _revision_from_path(path: str) -> str | None:
    parts = path.split("/")
    return parts[2] if len(parts) >= 4 else None


def _model_name_from_dir(model_dir: str) -> str:
    return model_dir.replace("__", "/")


def _format_score(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")
