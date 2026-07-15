from __future__ import annotations

import asyncio
import json
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Sequence

import httpx
import pyarrow.parquet as parquet

from .base import BaseSourceAdapter, RawSourceRecord, ScoreCandidate, compact_text, percent_score, safe_float, utc_now_iso


PATHS_URL = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/paths.json"
RAW_RESULTS_BASE_URL = "https://raw.githubusercontent.com/embeddings-benchmark/results/main/"
MTEB_RESULTS_FILTER_URL = "https://datasets-server.huggingface.co/filter"
MTEB_RESULTS_DATASET = "mteb/results"
MTEB_RESULTS_DATASET_API_URL = "https://huggingface.co/api/datasets/mteb/results"
MTEB_RESULTS_DATASET_TREE_BASE_URL = "https://huggingface.co/api/datasets/mteb/results/tree/"
MTEB_RESULTS_DATASET_RESOLVE_BASE_URL = "https://huggingface.co/datasets/mteb/results/resolve/"
RTEB_FINANCE_LEADERBOARD_URL = "https://huggingface.co/spaces/mteb/leaderboard?benchmark_name=RTEB%28fin%2C%20beta%29"
MTEB_RESULT_FETCH_BATCH_SIZE = 20
MTEB_RESULT_MAX_RETRIES = 3
MTEB_RETRY_BACKOFF_SECONDS = 0.25
MTEB_RETRY_MAX_DELAY_SECONDS = 30.0
RTEB_FINANCE_PAGE_SIZE = 100
RTEB_FINANCE_MAX_RETRIES = 3
RTEB_PARQUET_MAX_SHARDS = 8
RTEB_PARQUET_MAX_SHARD_BYTES = 128 * 1024 * 1024
RTEB_PARQUET_MAX_TOTAL_BYTES = 512 * 1024 * 1024
RTEB_PARQUET_MEMORY_LIMIT_BYTES = 8 * 1024 * 1024
_TASK_SELECTION_POLICY = (
    "one coherent model revision with greatest unique eligible task coverage; "
    "revision and task path ties resolve lexicographically"
)
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
RTEB_FINANCE_TASKS: dict[str, dict[str, Any]] = {
    "FinanceBenchRetrieval": {"is_public": True, "description": "financial document retrieval and Q&A"},
    "HC3FinanceRetrieval": {"is_public": True, "description": "financial Q&A retrieval"},
    "FinQARetrieval": {"is_public": True, "description": "financial question-answering retrieval"},
    "EnglishFinance1Retrieval": {"is_public": False, "description": "stock compensation, corporate governance, and SEC filing retrieval"},
    "EnglishFinance2Retrieval": {"is_public": False, "description": "financial performance and industry-metric retrieval"},
    "EnglishFinance3Retrieval": {"is_public": False, "description": "personal finance Q&A retrieval"},
    "EnglishFinance4Retrieval": {"is_public": False, "description": "personal finance advice retrieval"},
}


@dataclass(frozen=True, slots=True)
class _TaskPathSelection:
    paths: tuple[str, ...]
    selected_revision: str | None
    discovered_eligible_file_count: int


@dataclass(frozen=True, slots=True)
class _RecordFetchResult:
    record: RawSourceRecord | None
    failure: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class _PageFetchResult:
    payload: Any | None
    failure: dict[str, Any] | None


class MtebCoverageError(ValueError):
    """Raised when a selected MTEB task or RTEB page could not be fetched completely."""

    def __init__(self, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


def _retryable_status(status_code: int) -> bool:
    return status_code in {408, 425, 429} or status_code >= 500


def _is_deterministic_stale_path(failure: dict[str, Any] | None) -> bool:
    return bool(failure and failure.get("status_code") in {404, 410})


def _retry_delay_seconds(response: httpx.Response | None, attempt: int) -> float:
    retry_after = compact_text(response.headers.get("Retry-After")) if response is not None else ""
    if retry_after:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = MTEB_RETRY_BACKOFF_SECONDS * (2**attempt)
    else:
        delay = MTEB_RETRY_BACKOFF_SECONDS * (2**attempt)
    return min(MTEB_RETRY_MAX_DELAY_SECONDS, max(0.0, delay))


async def _request_json_object(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float,
    retries: int,
    params: dict[str, str] | None = None,
    reject_error_payload: bool = False,
    expected_type: type = dict,
) -> _PageFetchResult:
    last_failure: dict[str, Any] = {"error": "request did not run", "attempts": 0}
    for attempt in range(retries):
        response: httpx.Response | None = None
        try:
            response = await client.get(url, params=params, timeout=timeout)
            if _retryable_status(response.status_code):
                last_failure = {
                    "error": f"HTTP {response.status_code}",
                    "status_code": response.status_code,
                    "attempts": attempt + 1,
                    "retryable": True,
                }
            elif response.status_code >= 400:
                return _PageFetchResult(
                    payload=None,
                    failure={
                        "error": f"HTTP {response.status_code}",
                        "status_code": response.status_code,
                        "attempts": attempt + 1,
                        "retryable": False,
                    },
                )
            else:
                try:
                    payload = response.json()
                except (json.JSONDecodeError, ValueError) as exc:
                    last_failure = {
                        "error": f"invalid JSON: {exc}",
                        "status_code": response.status_code,
                        "attempts": attempt + 1,
                        "retryable": True,
                    }
                else:
                    if not isinstance(payload, expected_type):
                        last_failure = {
                            "error": f"response was not a JSON {expected_type.__name__}",
                            "status_code": response.status_code,
                            "attempts": attempt + 1,
                            "retryable": True,
                        }
                    elif reject_error_payload and isinstance(payload, dict) and payload.get("error"):
                        last_failure = {
                            "error": f"response error: {compact_text(payload.get('error'))}",
                            "status_code": response.status_code,
                            "attempts": attempt + 1,
                            "retryable": True,
                        }
                    else:
                        return _PageFetchResult(payload=payload, failure=None)
        except httpx.HTTPError as exc:
            last_failure = {
                "error": f"{type(exc).__name__}: {exc}",
                "attempts": attempt + 1,
                "retryable": True,
            }

        if attempt + 1 < retries:
            await asyncio.sleep(_retry_delay_seconds(response, attempt))

    return _PageFetchResult(payload=None, failure=last_failure)


class MtebAdapter(BaseSourceAdapter):
    source_id = "mteb"
    benchmark_ids = ("mteb_retrieval", "mteb_reranking", "mteb_retrieval_reranking", "rteb_finance")
    source_url = "https://github.com/embeddings-benchmark/results"

    async def fetch_raw(self, client: httpx.AsyncClient) -> list[RawSourceRecord]:
        self._set_fetch_details({})
        fetched_at = utc_now_iso()
        paths_result = await _request_json_object(
            client,
            PATHS_URL,
            timeout=30.0,
            retries=MTEB_RESULT_MAX_RETRIES,
        )
        if paths_result.payload is None:
            details = {
                "paths_model_count": 0,
                "paths_eligible_model_count": 0,
                "eligible_model_count": 0,
                "discovered_eligible_task_file_count": 0,
                "probed_task_file_count": 0,
                "accessible_task_file_count": 0,
                "stale_task_file_count": 0,
                "stale_task_files": [],
                "requested_task_file_count": 0,
                "fetched_task_record_count": 0,
                "failed_task_file_count": 0,
                "skipped_task_file_count": 0,
                "skipped_or_failed_task_count": 0,
                "failed_task_files": [],
                "selected_model_revisions": {},
                "probe_complete": False,
                "paths_request_failure": paths_result.failure,
                "per_model_task_file_cap": None,
                "batch_size": MTEB_RESULT_FETCH_BATCH_SIZE,
                "retries": MTEB_RESULT_MAX_RETRIES,
                "global_truncation": False,
                "selection_policy": _TASK_SELECTION_POLICY,
                "rteb_finance_coverage": _empty_rteb_coverage(),
                "total_fetched_record_count": 0,
            }
            self._set_fetch_details(details)
            raise MtebCoverageError("MTEB paths request failed after retries", details)
        paths_payload = paths_result.payload

        probe_requests: list[tuple[str, str]] = []
        paths_eligible_model_count = 0
        discovered_eligible_task_file_count = 0
        for raw_model_dir, raw_paths in sorted(
            paths_payload.items(),
            key=lambda item: (compact_text(item[0]).casefold(), compact_text(item[0])),
        ):
            if not isinstance(raw_paths, list):
                continue
            model_dir = compact_text(raw_model_dir)
            if not model_dir:
                continue
            eligible_paths = _eligible_task_paths(raw_paths)
            discovered_eligible_task_file_count += len(eligible_paths)
            if not eligible_paths:
                continue
            paths_eligible_model_count += 1

            for result_path in eligible_paths:
                probe_requests.append((model_dir, result_path))

        accessible_records_by_model: dict[str, dict[str, RawSourceRecord]] = defaultdict(dict)
        stale_task_files: list[dict[str, Any]] = []
        failed_task_files: list[dict[str, Any]] = []
        for batch_start in range(0, len(probe_requests), MTEB_RESULT_FETCH_BATCH_SIZE):
            batch = probe_requests[batch_start : batch_start + MTEB_RESULT_FETCH_BATCH_SIZE]
            fetched_records = await asyncio.gather(
                *(
                    _fetch_result_record(client, model_dir, result_path, fetched_at)
                    for model_dir, result_path in batch
                )
            )
            for (model_dir, result_path), fetched in zip(batch, fetched_records, strict=True):
                if fetched.record is not None:
                    accessible_records_by_model[model_dir][result_path] = fetched.record
                    continue
                failure = {
                    "model_dir": model_dir,
                    "model_name": _model_name_from_dir(model_dir),
                    "model_revision": _revision_from_path(result_path),
                    "task_name": _task_name_from_path(result_path),
                    "task_path": result_path,
                    **(fetched.failure or {"error": "task result could not be parsed"}),
                }
                if _is_deterministic_stale_path(fetched.failure):
                    stale_task_files.append(failure)
                else:
                    failed_task_files.append(failure)

        task_records: list[RawSourceRecord] = []
        selected_model_revisions: dict[str, str | None] = {}
        for model_dir, records_by_path in sorted(
            accessible_records_by_model.items(),
            key=lambda item: (item[0].casefold(), item[0]),
        ):
            selection = _select_task_paths(records_by_path)
            if not selection.paths:
                continue
            selected_model_revisions[model_dir] = selection.selected_revision
            task_records.extend(records_by_path[path] for path in selection.paths)

        rteb_finance_records, rteb_coverage, rteb_failures = await _fetch_rteb_finance_records(client, fetched_at)
        raw_records = [*task_records, *rteb_finance_records]
        accessible_task_file_count = sum(len(records) for records in accessible_records_by_model.values())
        skipped_task_file_count = max(0, accessible_task_file_count - len(task_records))
        details = {
            "paths_model_count": len(paths_payload),
            "paths_eligible_model_count": paths_eligible_model_count,
            "eligible_model_count": len(selected_model_revisions),
            "discovered_eligible_task_file_count": discovered_eligible_task_file_count,
            "probed_task_file_count": len(probe_requests),
            "accessible_task_file_count": accessible_task_file_count,
            "stale_task_file_count": len(stale_task_files),
            "stale_task_files": stale_task_files,
            "requested_task_file_count": len(task_records),
            "fetched_task_record_count": len(task_records),
            "failed_task_file_count": len(failed_task_files),
            "skipped_task_file_count": skipped_task_file_count,
            "skipped_or_failed_task_count": (
                skipped_task_file_count + len(stale_task_files) + len(failed_task_files)
            ),
            "failed_task_files": failed_task_files,
            "selected_model_revisions": selected_model_revisions,
            "probe_complete": not failed_task_files,
            "per_model_task_file_cap": None,
            "batch_size": MTEB_RESULT_FETCH_BATCH_SIZE,
            "retries": MTEB_RESULT_MAX_RETRIES,
            "global_truncation": False,
            "selection_policy": _TASK_SELECTION_POLICY,
            "rteb_finance_configured_task_count": len(RTEB_FINANCE_TASKS),
            "rteb_finance_fetched_record_count": len(rteb_finance_records),
            "rteb_finance_coverage": rteb_coverage,
            "total_fetched_record_count": len(raw_records),
        }
        self._set_fetch_details(details)
        if failed_task_files or rteb_failures:
            failure_count = len(failed_task_files) + len(rteb_failures)
            raise MtebCoverageError(
                f"MTEB source coverage incomplete after retries ({failure_count} failure(s))",
                details,
            )
        if not raw_records:
            raise ValueError("Could not parse any MTEB retrieval, reranking, or RTEB Finance result rows.")
        return raw_records

    def normalize(self, raw_records: Sequence[RawSourceRecord]) -> list[ScoreCandidate]:
        grouped: dict[tuple[str, str], list[RawSourceRecord]] = defaultdict(list)
        rteb_finance_records_by_model: dict[str, list[RawSourceRecord]] = defaultdict(list)
        for record in raw_records:
            if record.benchmark_id == "rteb_finance":
                rteb_finance_records_by_model[record.raw_model_key or record.raw_model_name].append(record)
                continue
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

        for model_key, records in rteb_finance_records_by_model.items():
            candidate = _rteb_finance_candidate(model_key, records)
            if candidate is not None:
                candidates.append(candidate)

        return candidates


async def _fetch_result_record(
    client: httpx.AsyncClient,
    model_dir: str,
    result_path: str,
    fetched_at: str,
) -> _RecordFetchResult:
    task_name = _task_name_from_path(result_path)
    category = _task_category(task_name)
    if category is None:
        return _RecordFetchResult(
            record=None,
            failure={"error": "task path is outside the retrieval/reranking selection policy", "attempts": 0},
        )

    source_url = f"{RAW_RESULTS_BASE_URL}{result_path}"
    fetched = await _request_json_object(
        client,
        source_url,
        timeout=30.0,
        retries=MTEB_RESULT_MAX_RETRIES,
    )
    if fetched.payload is None:
        return _RecordFetchResult(record=None, failure=fetched.failure)
    payload = fetched.payload

    score_entries = list(_score_entries(payload, category))
    main_scores = [percent_score(entry.get("main_score")) for _split_name, entry in score_entries]
    main_scores = [score for score in main_scores if score is not None]
    if not main_scores:
        return _RecordFetchResult(
            record=None,
            failure={"error": "result payload contained no parseable main scores", "attempts": 1},
        )

    value = round(sum(main_scores) / len(main_scores), 4)
    model_name = _model_name_from_dir(model_dir)
    model_revision = _revision_from_path(result_path)
    languages = sorted(
        {
            language
            for _split_name, entry in score_entries
            for language in _language_entries(entry.get("languages"))
        }
    )
    splits = sorted({split_name for split_name, _entry in score_entries if split_name})
    subsets = sorted(
        {
            subset
            for _split_name, entry in score_entries
            for subset in _string_values(entry.get("hf_subset") or entry.get("subset"))
        }
        | set(_string_values(payload.get("hf_subset") or payload.get("subset")))
    )
    dataset_revisions = _string_values(payload.get("dataset_revision"))
    mteb_versions = _string_values(payload.get("mteb_version"))

    metadata = {
        "model_provider": model_name.split("/", 1)[0] if "/" in model_name else None,
        "model_roles": ["embedding"] if category == "retrieval" else ["reranker"],
        "task_category": category,
        "task_name": compact_text(payload.get("task_name") or payload.get("mteb_dataset_name")) or task_name,
        "task_path": result_path,
        "model_revision": model_revision,
        "mteb_version": mteb_versions[0] if len(mteb_versions) == 1 else None,
        "mteb_versions": mteb_versions,
        "dataset_revision": dataset_revisions[0] if len(dataset_revisions) == 1 else None,
        "dataset_revisions": dataset_revisions,
        "languages": languages,
        "splits": splits,
        "subsets": subsets,
        "split_count": len(splits),
        "score_count": len(main_scores),
        "source_policy": "official_results_repo_task_main_score_average",
    }
    return _RecordFetchResult(
        record=RawSourceRecord(
            source_id="mteb",
            benchmark_id=f"mteb_{category}",
            raw_model_name=model_name,
            raw_model_key=model_name,
            raw_value=_format_score(value),
            source_url=source_url,
            collected_at=fetched_at,
            payload=payload,
            metadata=metadata,
        ),
        failure=None,
    )


def _empty_rteb_coverage() -> dict[str, Any]:
    return {
        "configured_task_count": len(RTEB_FINANCE_TASKS),
        "requested_task_count": 0,
        "completed_task_count": 0,
        "failed_task_count": 0,
        "tasks_with_records_count": 0,
        "requested_page_count": 0,
        "fetched_page_count": 0,
        "failed_page_count": 0,
        "fetched_record_count": 0,
        "invalid_row_count": 0,
        "failed_pages": [],
        "failed_rows": [],
    }


async def _fetch_rteb_finance_records(
    client: httpx.AsyncClient,
    fetched_at: str,
) -> tuple[list[RawSourceRecord], dict[str, Any], list[dict[str, Any]]]:
    records, coverage, failures = await _fetch_rteb_finance_dataset_server_records(client, fetched_at)
    coverage["mode"] = "dataset_server"
    if not failures or not _rteb_failures_allow_parquet_fallback(failures):
        return records, coverage, failures

    fallback_records, fallback_coverage, fallback_failures = await _fetch_rteb_finance_parquet_records(
        client,
        fetched_at,
    )
    fallback_coverage["mode"] = "parquet_fallback"
    fallback_coverage["dataset_server"] = coverage
    return fallback_records, fallback_coverage, fallback_failures


async def _fetch_rteb_finance_dataset_server_records(
    client: httpx.AsyncClient,
    fetched_at: str,
) -> tuple[list[RawSourceRecord], dict[str, Any], list[dict[str, Any]]]:
    raw_records: list[RawSourceRecord] = []
    coverage = _empty_rteb_coverage()
    failures: list[dict[str, Any]] = []
    for task_name, task_metadata in RTEB_FINANCE_TASKS.items():
        coverage["requested_task_count"] += 1
        offset = 0
        task_record_count = 0
        task_failed = False
        while True:
            coverage["requested_page_count"] += 1
            page = await _fetch_results_dataset_page(client, task_name, offset)
            if page.payload is None:
                failure = {
                    "task_name": task_name,
                    "offset": offset,
                    **(page.failure or {"error": "RTEB page request failed"}),
                }
                coverage["failed_page_count"] += 1
                coverage["failed_pages"].append(failure)
                failures.append({"kind": "rteb_page", **failure})
                task_failed = True
                break
            coverage["fetched_page_count"] += 1
            payload = page.payload

            rows = payload.get("rows")
            total_rows = _nonnegative_int(payload.get("num_rows_total"))
            if not isinstance(rows, list) or total_rows is None:
                failure = {
                    "task_name": task_name,
                    "offset": offset,
                    "error": "RTEB page omitted a rows list or valid num_rows_total",
                }
                coverage["failed_page_count"] += 1
                coverage["failed_pages"].append(failure)
                failures.append({"kind": "rteb_page", **failure})
                task_failed = True
                break
            if not rows:
                if offset < total_rows:
                    failure = {
                        "task_name": task_name,
                        "offset": offset,
                        "error": f"RTEB page ended before advertised total of {total_rows} rows",
                    }
                    coverage["failed_page_count"] += 1
                    coverage["failed_pages"].append(failure)
                    failures.append({"kind": "rteb_page", **failure})
                    task_failed = True
                break

            for row_index, item in enumerate(rows):
                row_payload = item.get("row") if isinstance(item, dict) else None
                actual_task_name = (
                    compact_text(row_payload.get("task_name"))
                    if isinstance(row_payload, dict)
                    else ""
                )
                if actual_task_name != task_name:
                    failure = {
                        "task_name": task_name,
                        "actual_task_name": actual_task_name or None,
                        "offset": offset,
                        "row_index": row_index,
                        "error": "RTEB row task_name did not match the requested task",
                    }
                    coverage["invalid_row_count"] += 1
                    coverage["failed_rows"].append(failure)
                    failures.append({"kind": "rteb_row", **failure})
                    task_failed = True
                    continue
                record = _rteb_finance_record_from_dataset_row(item, task_metadata, fetched_at)
                if record is None:
                    failure = {
                        "task_name": task_name,
                        "offset": offset,
                        "row_index": row_index,
                        "error": "RTEB row could not be normalized",
                    }
                    coverage["invalid_row_count"] += 1
                    coverage["failed_rows"].append(failure)
                    failures.append({"kind": "rteb_row", **failure})
                    task_failed = True
                    continue
                raw_records.append(record)
                task_record_count += 1

            offset += len(rows)
            if offset >= total_rows:
                break
        if not task_failed and task_record_count == 0:
            failure = {
                "task_name": task_name,
                "error": "RTEB task returned no valid records",
            }
            failures.append({"kind": "rteb_task_coverage", **failure})
            task_failed = True
        if task_failed:
            coverage["failed_task_count"] += 1
        else:
            coverage["completed_task_count"] += 1
        if task_record_count:
            coverage["tasks_with_records_count"] += 1

    coverage["fetched_record_count"] = len(raw_records)
    return raw_records if not failures else [], coverage, failures


def _rteb_failures_allow_parquet_fallback(failures: Sequence[dict[str, Any]]) -> bool:
    return bool(failures) and all(
        failure.get("kind") == "rteb_page" and bool(failure.get("retryable"))
        for failure in failures
    )


async def _fetch_rteb_finance_parquet_records(
    client: httpx.AsyncClient,
    fetched_at: str,
) -> tuple[list[RawSourceRecord], dict[str, Any], list[dict[str, Any]]]:
    coverage = _empty_rteb_coverage()
    coverage.update(
        {
            "requested_task_count": len(RTEB_FINANCE_TASKS),
            "selected_shard_count": 0,
            "requested_shard_count": 0,
            "fetched_shard_count": 0,
            "failed_shard_count": 0,
            "manifest_total_bytes": 0,
            "downloaded_bytes": 0,
            "dataset_revision": None,
            "shards": [],
        }
    )
    failures: list[dict[str, Any]] = []

    dataset_info = await _request_json_object(
        client,
        MTEB_RESULTS_DATASET_API_URL,
        timeout=30.0,
        retries=RTEB_FINANCE_MAX_RETRIES,
    )
    if dataset_info.payload is None:
        failure = {"kind": "rteb_parquet_manifest", **(dataset_info.failure or {})}
        failures.append(failure)
        coverage["manifest_failure"] = failure
        coverage["failed_task_count"] = len(RTEB_FINANCE_TASKS)
        return [], coverage, failures

    dataset_revision = compact_text(dataset_info.payload.get("sha"))
    if not dataset_revision:
        failure = {"kind": "rteb_parquet_manifest", "error": "dataset API omitted its revision sha"}
        failures.append(failure)
        coverage["manifest_failure"] = failure
        coverage["failed_task_count"] = len(RTEB_FINANCE_TASKS)
        return [], coverage, failures
    coverage["dataset_revision"] = dataset_revision

    tree_url = (
        f"{MTEB_RESULTS_DATASET_TREE_BASE_URL}{dataset_revision}/data"
        "?recursive=true&expand=false"
    )
    manifest = await _request_json_object(
        client,
        tree_url,
        timeout=30.0,
        retries=RTEB_FINANCE_MAX_RETRIES,
        expected_type=list,
    )
    if manifest.payload is None:
        failure = {"kind": "rteb_parquet_manifest", **(manifest.failure or {})}
        failures.append(failure)
        coverage["manifest_failure"] = failure
        coverage["failed_task_count"] = len(RTEB_FINANCE_TASKS)
        return [], coverage, failures

    shards = sorted(
        (
            {"path": compact_text(item.get("path")), "size": _nonnegative_int(item.get("size"))}
            for item in manifest.payload
            if isinstance(item, dict)
            and compact_text(item.get("path")).endswith(".parquet")
            and compact_text(item.get("type")) == "file"
        ),
        key=lambda item: (str(item["path"]).casefold(), str(item["path"])),
    )
    invalid_manifest = (
        not shards
        or len(shards) > RTEB_PARQUET_MAX_SHARDS
        or any(item["size"] is None or int(item["size"]) > RTEB_PARQUET_MAX_SHARD_BYTES for item in shards)
    )
    total_bytes = sum(int(item["size"] or 0) for item in shards)
    if invalid_manifest or total_bytes > RTEB_PARQUET_MAX_TOTAL_BYTES:
        failure = {
            "kind": "rteb_parquet_manifest",
            "error": "parquet manifest exceeded the configured shard or byte bounds",
            "shard_count": len(shards),
            "total_bytes": total_bytes,
        }
        failures.append(failure)
        coverage["manifest_failure"] = failure
        coverage["failed_task_count"] = len(RTEB_FINANCE_TASKS)
        return [], coverage, failures

    coverage["selected_shard_count"] = len(shards)
    coverage["manifest_total_bytes"] = total_bytes
    parquet_rows: list[dict[str, Any]] = []
    for shard in shards:
        coverage["requested_shard_count"] += 1
        rows, shard_details, shard_failure = await _fetch_rteb_parquet_shard_rows(
            client,
            dataset_revision,
            str(shard["path"]),
            int(shard["size"] or 0),
        )
        coverage["shards"].append(shard_details)
        if shard_failure is not None:
            coverage["failed_shard_count"] += 1
            failures.append({"kind": "rteb_parquet_shard", **shard_failure})
            break
        coverage["fetched_shard_count"] += 1
        coverage["downloaded_bytes"] += int(shard_details.get("downloaded_bytes") or 0)
        parquet_rows.extend(rows)

    if failures:
        coverage["failed_task_count"] = len(RTEB_FINANCE_TASKS)
        return [], coverage, failures

    records: list[RawSourceRecord] = []
    tasks_with_records: set[str] = set()
    failed_tasks: set[str] = set()
    for row_index, row in enumerate(parquet_rows):
        task_name = compact_text(row.get("task_name"))
        task_metadata = RTEB_FINANCE_TASKS.get(task_name)
        if task_metadata is None:
            continue
        row["dataset_revision"] = dataset_revision
        record = _rteb_finance_record_from_dataset_row({"row": row}, task_metadata, fetched_at)
        if record is None:
            failure = {
                "kind": "rteb_parquet_row",
                "task_name": task_name,
                "row_index": row_index,
                "error": "filtered parquet row could not be normalized",
            }
            failures.append(failure)
            coverage["failed_rows"].append(failure)
            coverage["invalid_row_count"] += 1
            failed_tasks.add(task_name)
            continue
        records.append(record)
        tasks_with_records.add(task_name)

    missing_tasks = sorted(set(RTEB_FINANCE_TASKS) - tasks_with_records)
    if missing_tasks:
        failure = {
            "kind": "rteb_parquet_coverage",
            "error": "authoritative parquet snapshot omitted configured RTEB tasks",
            "missing_tasks": missing_tasks,
        }
        failures.append(failure)
        failed_tasks.update(missing_tasks)

    coverage["tasks_with_records_count"] = len(tasks_with_records)
    coverage["completed_task_count"] = len(set(RTEB_FINANCE_TASKS) - failed_tasks)
    coverage["failed_task_count"] = len(failed_tasks)
    coverage["fetched_record_count"] = len(records)
    return records if not failures else [], coverage, failures


async def _fetch_rteb_parquet_shard_rows(
    client: httpx.AsyncClient,
    dataset_revision: str,
    shard_path: str,
    expected_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    url = f"{MTEB_RESULTS_DATASET_RESOLVE_BASE_URL}{dataset_revision}/{shard_path}?download=true"
    last_failure: dict[str, Any] = {"error": "parquet download did not run", "attempts": 0}
    for attempt in range(RTEB_FINANCE_MAX_RETRIES):
        response_for_delay: httpx.Response | None = None
        try:
            async with client.stream("GET", url, timeout=120.0) as response:
                response_for_delay = response
                if _retryable_status(response.status_code):
                    last_failure = {
                        "path": shard_path,
                        "error": f"HTTP {response.status_code}",
                        "status_code": response.status_code,
                        "attempts": attempt + 1,
                        "retryable": True,
                    }
                elif response.status_code >= 400:
                    return [], {}, {
                        "path": shard_path,
                        "error": f"HTTP {response.status_code}",
                        "status_code": response.status_code,
                        "attempts": attempt + 1,
                        "retryable": False,
                    }
                else:
                    content_length = _nonnegative_int(response.headers.get("Content-Length"))
                    if content_length is not None and content_length > RTEB_PARQUET_MAX_SHARD_BYTES:
                        return [], {}, {
                            "path": shard_path,
                            "error": "parquet response exceeded the configured shard byte bound",
                            "attempts": attempt + 1,
                            "retryable": False,
                        }
                    with tempfile.SpooledTemporaryFile(
                        max_size=RTEB_PARQUET_MEMORY_LIMIT_BYTES,
                        mode="w+b",
                    ) as shard_file:
                        downloaded_bytes = 0
                        async for chunk in response.aiter_bytes():
                            downloaded_bytes += len(chunk)
                            if downloaded_bytes > RTEB_PARQUET_MAX_SHARD_BYTES:
                                return [], {}, {
                                    "path": shard_path,
                                    "error": "parquet download exceeded the configured shard byte bound",
                                    "attempts": attempt + 1,
                                    "retryable": False,
                                }
                            shard_file.write(chunk)
                        if expected_size and downloaded_bytes != expected_size:
                            last_failure = {
                                "path": shard_path,
                                "error": f"downloaded {downloaded_bytes} bytes; expected {expected_size}",
                                "attempts": attempt + 1,
                                "retryable": True,
                            }
                        else:
                            shard_file.seek(0)
                            rows = await asyncio.to_thread(_read_rteb_parquet_rows, shard_file)
                            return rows, {
                                "path": shard_path,
                                "expected_bytes": expected_size,
                                "downloaded_bytes": downloaded_bytes,
                                "filtered_row_count": len(rows),
                            }, None
        except (httpx.HTTPError, OSError, ValueError) as exc:
            last_failure = {
                "path": shard_path,
                "error": f"{type(exc).__name__}: {exc}",
                "attempts": attempt + 1,
                "retryable": True,
            }
        if attempt + 1 < RTEB_FINANCE_MAX_RETRIES:
            await asyncio.sleep(_retry_delay_seconds(response_for_delay, attempt))

    return [], {}, last_failure


def _read_rteb_parquet_rows(shard_file: Any) -> list[dict[str, Any]]:
    table = parquet.read_table(
        shard_file,
        columns=[
            "model_name",
            "model_revision",
            "task_name",
            "split",
            "language",
            "subset",
            "score",
            "is_public",
            "trained_on",
        ],
        filters=[("task_name", "in", sorted(RTEB_FINANCE_TASKS))],
        use_threads=True,
    )
    return table.to_pylist()


async def _fetch_results_dataset_page(
    client: httpx.AsyncClient,
    task_name: str,
    offset: int,
) -> _PageFetchResult:
    where = f"\"task_name\"='{task_name}'"
    params = {
        "dataset": MTEB_RESULTS_DATASET,
        "config": "default",
        "split": "train",
        "where": where,
        "offset": str(offset),
        "length": str(RTEB_FINANCE_PAGE_SIZE),
    }
    return await _request_json_object(
        client,
        MTEB_RESULTS_FILTER_URL,
        params=params,
        timeout=90.0,
        retries=RTEB_FINANCE_MAX_RETRIES,
        reject_error_payload=True,
    )


def _rteb_finance_record_from_dataset_row(
    item: Any,
    task_metadata: dict[str, Any],
    fetched_at: str,
) -> RawSourceRecord | None:
    if not isinstance(item, dict) or not isinstance(item.get("row"), dict):
        return None
    row = item["row"]
    model_name = compact_text(row.get("model_name"))
    task_name = compact_text(row.get("task_name"))
    score = percent_score(row.get("score"))
    if not model_name or not task_name or score is None:
        return None

    languages = _language_entries(row.get("language"))
    subset = compact_text(row.get("hf_subset") or row.get("subset")) or None
    metadata = {
        "model_provider": model_name.split("/", 1)[0] if "/" in model_name else None,
        "model_roles": ["embedding"],
        "task_category": "retrieval",
        "task_name": task_name,
        "task_description": compact_text(task_metadata.get("description")) or None,
        "benchmark_group": "RTEB(fin, beta)",
        "benchmark_name": "RTEB Finance",
        "model_revision": compact_text(row.get("model_revision")) or None,
        "dataset_revision": compact_text(row.get("dataset_revision")) or None,
        "split": compact_text(row.get("split")) or None,
        "subset": subset,
        "hf_subset": compact_text(row.get("hf_subset")) or None,
        "languages": languages,
        "is_public": bool(row.get("is_public")),
        "task_is_public": bool(task_metadata.get("is_public")),
        "trained_on": bool(row.get("trained_on")),
        "source_policy": "official_mteb_results_dataset_rteb_finance_score",
    }
    return RawSourceRecord(
        source_id="mteb",
        benchmark_id="rteb_finance",
        raw_model_name=model_name,
        raw_model_key=model_name,
        raw_value=_format_score(score),
        source_url=RTEB_FINANCE_LEADERBOARD_URL,
        collected_at=fetched_at,
        payload=row,
        metadata=metadata,
    )


def _select_task_paths(paths: Iterable[Any]) -> _TaskPathSelection:
    eligible_paths = set(_eligible_task_paths(paths))
    by_revision: dict[str, dict[tuple[str, str], set[str]]] = defaultdict(lambda: defaultdict(set))
    for result_path in eligible_paths:
        task_name = _task_name_from_path(result_path)
        category = _task_category(task_name)
        assert category is not None
        revision = _revision_from_path(result_path) or ""
        by_revision[revision][(category, task_name.casefold())].add(result_path)

    if not by_revision:
        return _TaskPathSelection(paths=(), selected_revision=None, discovered_eligible_file_count=0)

    selected_revision, selected_tasks = sorted(
        by_revision.items(),
        key=lambda item: (-len(item[1]), item[0].casefold(), item[0]),
    )[0]
    selected_paths = tuple(
        min(task_paths, key=lambda path: (path.casefold(), path))
        for _task_key, task_paths in sorted(
            selected_tasks.items(),
            key=lambda item: (0 if item[0][0] == "retrieval" else 1, item[0][1]),
        )
    )
    return _TaskPathSelection(
        paths=selected_paths,
        selected_revision=selected_revision or None,
        discovered_eligible_file_count=len(eligible_paths),
    )


def _eligible_task_paths(paths: Iterable[Any]) -> list[str]:
    eligible_paths = {
        result_path
        for raw_path in paths
        if (result_path := compact_text(raw_path)).endswith(".json")
        and _task_category(_task_name_from_path(result_path)) is not None
    }
    return sorted(
        eligible_paths,
        key=lambda path: (
            compact_text(_revision_from_path(path)).casefold(),
            compact_text(_revision_from_path(path)),
            0 if _task_category(_task_name_from_path(path)) == "retrieval" else 1,
            _task_name_from_path(path).casefold(),
            path.casefold(),
            path,
        ),
    )


def _selected_task_paths(paths: Iterable[Any]) -> list[str]:
    """Compatibility wrapper returning the deterministic coherent-revision task paths."""
    return list(_select_task_paths(paths).paths)


def _category_candidate(model_key: str, category: str, records: list[RawSourceRecord]) -> ScoreCandidate | None:
    scored_records = _scored_records(records)
    if not scored_records:
        return None

    valid_records = [record for record, _score in scored_records]
    scores = [score for _record, score in scored_records]
    value = round(sum(scores) / len(scores), 4)
    first_record = valid_records[0]
    benchmark_id = f"mteb_{category}"
    role = "embedding" if category == "retrieval" else "reranker"
    task_names = sorted(
        {
            compact_text(record.metadata.get("task_name"))
            for record in valid_records
            if compact_text(record.metadata.get("task_name"))
        }
    )
    languages = sorted(
        {
            language
            for record in valid_records
            for language in _language_entries(record.metadata.get("languages"))
        }
    )
    model_revisions = _metadata_values(valid_records, "model_revision")
    dataset_revisions = _metadata_values(valid_records, "dataset_revisions", "dataset_revision")
    mteb_versions = _metadata_values(valid_records, "mteb_versions", "mteb_version")
    splits = _metadata_values(valid_records, "splits", "split")
    subsets = _metadata_values(valid_records, "subsets", "hf_subset", "subset")
    source_metadata = _compact_metadata(
        {
            "task_category": category,
            "task_names": task_names,
            "languages": languages,
            "model_revision": "|".join(model_revisions) if model_revisions else None,
            "dataset_revision": "|".join(dataset_revisions) if dataset_revisions else None,
            "dataset_revisions": dataset_revisions,
            "mteb_version": "|".join(mteb_versions) if mteb_versions else None,
            "mteb_versions": mteb_versions,
            "splits": splits,
            "subsets": subsets,
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
        observation_count=len(scores),
        source_metadata=source_metadata,
        metadata={
            "model_provider": first_record.metadata.get("model_provider"),
            "model_roles": [role],
            "task_category": category,
            "task_names": task_names,
            "languages": languages,
            "splits": splits,
            "subsets": subsets,
            "score_count": len(scores),
            "source_policy": "official_results_repo_category_main_score_average",
        },
    )


def _combined_candidate(model_key: str, records: list[RawSourceRecord]) -> ScoreCandidate | None:
    scored_records = _scored_records(records)
    if not scored_records:
        return None

    valid_records = [record for record, _score in scored_records]
    scores = [score for _record, score in scored_records]
    value = round(sum(scores) / len(scores), 4)
    first_record = valid_records[0]
    task_categories = sorted(
        {
            compact_text(record.metadata.get("task_category"))
            for record in valid_records
            if compact_text(record.metadata.get("task_category"))
        }
    )
    task_names = sorted(
        {
            compact_text(record.metadata.get("task_name"))
            for record in valid_records
            if compact_text(record.metadata.get("task_name"))
        }
    )
    languages = sorted(
        {
            language
            for record in valid_records
            for language in _language_entries(record.metadata.get("languages"))
        }
    )
    model_revisions = _metadata_values(valid_records, "model_revision")
    dataset_revisions = _metadata_values(valid_records, "dataset_revisions", "dataset_revision")
    mteb_versions = _metadata_values(valid_records, "mteb_versions", "mteb_version")
    splits = _metadata_values(valid_records, "splits", "split")
    subsets = _metadata_values(valid_records, "subsets", "hf_subset", "subset")
    source_metadata = _compact_metadata(
        {
            "task_categories": task_categories,
            "task_names": task_names,
            "languages": languages,
            "model_revision": "|".join(model_revisions) if model_revisions else None,
            "dataset_revision": "|".join(dataset_revisions) if dataset_revisions else None,
            "dataset_revisions": dataset_revisions,
            "mteb_version": "|".join(mteb_versions) if mteb_versions else None,
            "mteb_versions": mteb_versions,
            "splits": splits,
            "subsets": subsets,
        }
    )
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
        observation_count=len(scores),
        source_metadata=source_metadata,
        metadata={
            "model_provider": first_record.metadata.get("model_provider"),
            "model_roles": ["embedding", "reranker"],
            "task_categories": task_categories,
            "task_names": task_names,
            "languages": languages,
            "splits": splits,
            "subsets": subsets,
            "score_count": len(scores),
            "source_policy": "official_results_repo_retrieval_reranking_average",
        },
    )


def _rteb_finance_candidate(model_key: str, records: list[RawSourceRecord]) -> ScoreCandidate | None:
    scored_records = _scored_records(records)
    if not scored_records:
        return None

    valid_records = [record for record, _score in scored_records]
    scores = [score for _record, score in scored_records]
    value = round(sum(scores) / len(scores), 4)
    first_record = valid_records[0]
    task_names = sorted(
        {
            compact_text(record.metadata.get("task_name"))
            for record in valid_records
            if compact_text(record.metadata.get("task_name"))
        }
    )
    languages = sorted(
        {
            language
            for record in valid_records
            for language in _language_entries(record.metadata.get("languages"))
        }
    )
    public_rows = sum(1 for record in valid_records if bool(record.metadata.get("is_public")))
    private_rows = len(valid_records) - public_rows
    trained_on_rows = sum(1 for record in valid_records if bool(record.metadata.get("trained_on")))
    model_revisions = _metadata_values(valid_records, "model_revision")
    dataset_revisions = _metadata_values(valid_records, "dataset_revisions", "dataset_revision")
    splits = _metadata_values(valid_records, "splits", "split")
    subsets = _metadata_values(valid_records, "subsets", "hf_subset", "subset")
    source_metadata = _compact_metadata(
        {
            "task_category": "retrieval",
            "benchmark_group": "RTEB(fin, beta)",
            "task_names": task_names,
            "languages": languages,
            "model_revision": "|".join(model_revisions) if model_revisions else None,
            "dataset_revision": "|".join(dataset_revisions) if dataset_revisions else None,
            "dataset_revisions": dataset_revisions,
            "splits": splits,
            "subsets": subsets,
        }
    )
    return ScoreCandidate(
        source_id="mteb",
        benchmark_id="rteb_finance",
        raw_model_name=first_record.raw_model_name,
        raw_model_key=model_key,
        value=value,
        raw_value=_format_score(value),
        source_url=RTEB_FINANCE_LEADERBOARD_URL,
        collected_at=first_record.collected_at,
        source_type="primary",
        verified=True,
        notes=(
            f"Official RTEB Finance average across {len(scores)} task result row(s), "
            f"including {private_rows} closed/private row(s)."
        ),
        observation_count=len(scores),
        source_metadata=source_metadata,
        metadata={
            "model_provider": first_record.metadata.get("model_provider"),
            "model_roles": ["embedding"],
            "task_category": "retrieval",
            "benchmark_group": "RTEB(fin, beta)",
            "benchmark_name": "RTEB Finance",
            "task_names": task_names,
            "languages": languages,
            "splits": splits,
            "subsets": subsets,
            "score_count": len(scores),
            "public_row_count": public_rows,
            "private_row_count": private_rows,
            "trained_on_row_count": trained_on_rows,
            "source_policy": "official_mteb_results_dataset_rteb_finance_average",
        },
    )


def _scored_records(records: Iterable[RawSourceRecord]) -> list[tuple[RawSourceRecord, float]]:
    payload: list[tuple[RawSourceRecord, float]] = []
    for record in records:
        score = safe_float(record.raw_value)
        if score is not None:
            payload.append((record, score))
    return payload


def _string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        values = [item for nested in value.values() for item in _string_values(nested)]
        return sorted(set(values))
    if isinstance(value, (list, tuple, set)):
        values = [item for nested in value for item in _string_values(nested)]
        return sorted(set(values))
    text = compact_text(value)
    return [text] if text else []


def _metadata_values(records: Iterable[RawSourceRecord], *keys: str) -> list[str]:
    values = {
        value
        for record in records
        for key in keys
        for value in _string_values(record.metadata.get(key))
    }
    return sorted(values)


def _compact_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != "" and value != []
    }


def _score_entries(payload: dict[str, Any], category: str) -> Iterable[tuple[str, dict[str, Any]]]:
    scores_payload = payload.get("scores")
    if isinstance(scores_payload, dict):
        split_items = scores_payload.items()
    else:
        split_items = (
            (key, value)
            for key, value in payload.items()
            if key not in {"dataset_revision", "mteb_dataset_name", "mteb_version", "task_name"}
        )

    for raw_split_name, split_entries in split_items:
        split_name = compact_text(raw_split_name)
        entries = split_entries if isinstance(split_entries, list) else [split_entries]
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            entry = dict(raw_entry)
            if entry.get("main_score") is not None:
                yield split_name, entry
                continue

            legacy_main_score = _legacy_main_score(entry, category)
            if legacy_main_score is not None:
                entry["main_score"] = legacy_main_score
                yield split_name, entry
                continue

            for language_entry in _legacy_language_score_entries(entry, category):
                yield split_name, language_entry


def _legacy_main_score(entry: dict[str, Any], category: str) -> Any:
    if category == "retrieval":
        for metric_name in ("ndcg_at_10", "p-MRR"):
            value = entry.get(metric_name)
            if value is not None:
                return value
        return None
    if category == "reranking":
        return entry.get("map")
    return None


def _legacy_language_score_entries(
    entry: dict[str, Any],
    category: str,
) -> Iterable[dict[str, Any]]:
    if category != "retrieval":
        return
    for raw_language, raw_language_entry in sorted(
        entry.items(),
        key=lambda item: (compact_text(item[0]).casefold(), compact_text(item[0])),
    ):
        language = _legacy_language_name(raw_language)
        if language is None or not isinstance(raw_language_entry, dict):
            continue
        main_score = _legacy_main_score(raw_language_entry, category)
        if main_score is None:
            continue
        language_entry = dict(raw_language_entry)
        language_entry["main_score"] = main_score
        if not _language_entries(language_entry.get("languages")):
            language_entry["languages"] = [language]
        yield language_entry


def _legacy_language_name(value: Any) -> str | None:
    language = compact_text(value)
    parts = language.replace("_", "-").split("-")
    if (
        not language
        or len(parts[0]) not in {2, 3}
        or not all(part.isalpha() and 2 <= len(part) <= 8 for part in parts)
    ):
        return None
    return language


def _nonnegative_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


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
