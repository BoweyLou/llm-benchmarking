"""Seed data and idempotent bootstrap helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine

from .database import benchmarks, models, scores, utc_now_iso

BENCHMARKS: list[dict[str, Any]] = [
    {
        "id": "aa_intelligence",
        "name": "AA Intelligence Index",
        "short": "AA Intel",
        "source": "Artificial Analysis",
        "url": "https://artificialanalysis.ai/leaderboards/models",
        "category": "General Quality",
        "metric": "Index Score",
        "higher_is_better": 1,
        "tier": 1,
        "scraper_id": "ArtificialAnalysisAdapter",
        "description": "Composite quality index across multiple tasks. Best single number for overall capability.",
        "active": 1,
    },
    {
        "id": "gpqa_diamond",
        "name": "GPQA Diamond",
        "short": "GPQA-D",
        "source": "Epoch AI",
        "url": "https://epoch.ai/benchmarks/gpqa-diamond",
        "category": "Reasoning & Math",
        "metric": "Accuracy %",
        "higher_is_better": 1,
        "tier": 2,
        "scraper_id": "EpochGpqaAdapter",
        "description": "Graduate-level science questions. Highly resistant to contamination.",
        "active": 1,
    },
    {
        "id": "mmmu",
        "name": "MMMU",
        "short": "MMMU",
        "source": "MMMU team",
        "url": "https://mmmu-benchmark.github.io/",
        "category": "Multimodal",
        "metric": "Accuracy %",
        "higher_is_better": 1,
        "tier": 2,
        "scraper_id": "MmmuAdapter",
        "description": "College-level multimodal questions across many subjects.",
        "active": 1,
    },
    {
        "id": "swebench_verified",
        "name": "SWE-bench Verified",
        "short": "SWE-V",
        "source": "SWE-bench team",
        "url": "https://www.swebench.com/",
        "category": "Coding",
        "metric": "% Issues Resolved",
        "higher_is_better": 1,
        "tier": 1,
        "scraper_id": "SwebenchAdapter",
        "description": "Real GitHub issue resolution. Strong coding benchmark for production relevance.",
        "active": 1,
    },
    {
        "id": "ifeval",
        "name": "IFEval",
        "short": "IFEval",
        "source": "Google Research",
        "url": "https://llm-stats.com/benchmarks/ifeval",
        "category": "Instruction Following",
        "metric": "Prompt Accuracy %",
        "higher_is_better": 1,
        "tier": 2,
        "scraper_id": "IfevalAdapter",
        "description": "Machine-scoreable instruction constraints. Predictive of enterprise reliability.",
        "active": 1,
    },
    {
        "id": "terminal_bench",
        "name": "Terminal-Bench 2.0",
        "short": "Term-B",
        "source": "tbench.ai",
        "url": "https://www.tbench.ai/leaderboard/terminal-bench/2.0",
        "category": "Agentic & Tool Use",
        "metric": "% Tasks Resolved",
        "higher_is_better": 1,
        "tier": 2,
        "scraper_id": "TerminalBenchAdapter",
        "description": "Real workflow terminal tasks. Current policy derives one score per model from the best verified single-model submission.",
        "active": 1,
    },
    {
        "id": "ailuminate",
        "name": "AILuminate",
        "short": "Safety",
        "source": "MLCommons",
        "url": "https://ailuminate.mlcommons.org/benchmarks/",
        "category": "Safety & Compliance",
        "metric": "Grade (0-100)",
        "higher_is_better": 1,
        "tier": 1,
        "scraper_id": "AILuminateAdapter",
        "description": "Private test sets. English/French results are public HTML; other families remain anonymized.",
        "active": 1,
    },
    {
        "id": "aa_speed",
        "name": "Output Speed",
        "short": "Speed",
        "source": "Artificial Analysis",
        "url": "https://artificialanalysis.ai/leaderboards/models",
        "category": "Latency & Cost",
        "metric": "Tokens/sec",
        "higher_is_better": 1,
        "tier": 1,
        "scraper_id": "ArtificialAnalysisAdapter",
        "description": "Output tokens per second. Critical for real-time and high-concurrency systems.",
        "active": 1,
    },
    {
        "id": "aa_cost",
        "name": "Cost (blended)",
        "short": "Cost",
        "source": "Artificial Analysis",
        "url": "https://artificialanalysis.ai/leaderboards/models",
        "category": "Latency & Cost",
        "metric": "$/1M tokens",
        "higher_is_better": 0,
        "tier": 1,
        "scraper_id": "ArtificialAnalysisAdapter",
        "description": "Blended 3:1 input-output pricing. Lower is better.",
        "active": 1,
    },
    {
        "id": "chatbot_arena",
        "name": "Chatbot Arena",
        "short": "Arena ELO",
        "source": "LMSYS",
        "url": "https://arena.ai/leaderboard/text",
        "category": "General Quality",
        "metric": "ELO Score",
        "higher_is_better": 1,
        "tier": 1,
        "scraper_id": "ChatbotArenaAdapter",
        "description": "ELO from blind human preference votes.",
        "active": 1,
    },
]

MODELS: list[dict[str, Any]] = [
    {
        "id": "gemini-3-1-pro",
        "name": "Gemini 3.1 Pro Preview",
        "provider": "Google",
        "type": "proprietary",
        "release_date": "2026-Q1",
        "context_window": "1M tokens",
        "active": 1,
    },
    {
        "id": "gpt-5-4",
        "name": "GPT-5.4 (xhigh)",
        "provider": "OpenAI",
        "type": "proprietary",
        "release_date": "2026-Q1",
        "context_window": "128k tokens",
        "active": 1,
    },
    {
        "id": "gpt-5-3-codex",
        "name": "GPT-5.3 Codex (xhigh)",
        "provider": "OpenAI",
        "type": "proprietary",
        "release_date": "2026-Q1",
        "context_window": "128k tokens",
        "active": 1,
    },
    {
        "id": "claude-opus-4-6",
        "name": "Claude Opus 4.6",
        "provider": "Anthropic",
        "type": "proprietary",
        "release_date": "2025",
        "context_window": "200k tokens",
        "active": 1,
    },
    {
        "id": "claude-sonnet-4-6",
        "name": "Claude Sonnet 4.6",
        "provider": "Anthropic",
        "type": "proprietary",
        "release_date": "2025",
        "context_window": "200k tokens",
        "active": 1,
    },
    {
        "id": "o4-mini-high",
        "name": "o4 Mini High",
        "provider": "OpenAI",
        "type": "proprietary",
        "release_date": "2025",
        "context_window": "128k tokens",
        "active": 1,
    },
    {
        "id": "glm-5",
        "name": "GLM-5 (Reasoning)",
        "provider": "Zhipu AI",
        "type": "open_weights",
        "release_date": "2026-Q1",
        "context_window": "128k tokens",
        "active": 1,
    },
    {
        "id": "gemini-2-5-flash",
        "name": "Gemini 2.5 Flash-Lite (Reasoning)",
        "provider": "Google",
        "type": "proprietary",
        "release_date": "2025",
        "context_window": "1M tokens",
        "active": 1,
    },
    {
        "id": "mercury-2",
        "name": "Mercury 2",
        "provider": "Inception Labs",
        "type": "proprietary",
        "release_date": "2026-Q1",
        "context_window": "32k tokens",
        "active": 1,
    },
    {
        "id": "gemma-3n-e4b",
        "name": "Gemma 3n E4B Instruct",
        "provider": "Google",
        "type": "open_weights",
        "release_date": "2026-Q1",
        "context_window": "8k tokens",
        "active": 1,
    },
]

USE_CASES: list[dict[str, Any]] = [
    {
        "id": "general_reasoning",
        "label": "General Reasoning",
        "icon": "🧠",
        "description": "Logic, multi-step problem solving, knowledge-intensive tasks",
        "weights": {"aa_intelligence": 0.40, "gpqa_diamond": 0.35, "chatbot_arena": 0.25},
    },
    {
        "id": "coding",
        "label": "Coding & Engineering",
        "icon": "💻",
        "description": "Code generation, debugging, repo-level tasks, DevOps",
        "weights": {"swebench_verified": 0.55, "aa_intelligence": 0.25, "terminal_bench": 0.20},
    },
    {
        "id": "agentic",
        "label": "Agentic & Tool Use",
        "icon": "🤖",
        "description": "Multi-step workflows, API calls, terminal and browser automation",
        "weights": {"terminal_bench": 0.50, "swebench_verified": 0.25, "aa_intelligence": 0.25},
    },
    {
        "id": "safety_compliance",
        "label": "Safety & Compliance",
        "icon": "🛡️",
        "description": "Harmful output avoidance, hazard categories, regulatory readiness",
        "weights": {"ailuminate": 0.70, "aa_intelligence": 0.30},
    },
    {
        "id": "cost_efficiency",
        "label": "Cost Efficiency",
        "icon": "💰",
        "description": "Minimise spend while maintaining quality for high-volume use",
        "weights": {"aa_cost": 0.60, "aa_speed": 0.25, "aa_intelligence": 0.15},
    },
    {
        "id": "multimodal",
        "label": "Multimodal",
        "icon": "🖼️",
        "description": "Vision-language, chart understanding, document image processing",
        "weights": {"mmmu": 0.65, "aa_intelligence": 0.35},
    },
    {
        "id": "instruction_following",
        "label": "Instruction Following",
        "icon": "📋",
        "description": "Strict adherence to constraints, formatting rules, complex prompt structures",
        "weights": {"ifeval": 0.75, "chatbot_arena": 0.25},
    },
    {
        "id": "speed",
        "label": "Speed / Latency",
        "icon": "⚡",
        "description": "Maximum throughput for real-time, streaming, or high-concurrency apps",
        "weights": {"aa_speed": 0.80, "aa_intelligence": 0.20},
    },
]

AILUMINATE_GRADE_TO_SCORE: dict[str, float] = {
    "Poor": 0.0,
    "Fair": 25.0,
    "Good": 50.0,
    "VeryGood": 75.0,
    "Very Good": 75.0,
    "Excellent": 100.0,
}

SEED_SCORES: list[dict[str, Any]] = [
    {"model_id": "gemini-3-1-pro", "benchmark_id": "aa_intelligence", "value": 57.0, "raw_value": "57"},
    {"model_id": "gpt-5-4", "benchmark_id": "aa_intelligence", "value": 57.0, "raw_value": "57"},
    {"model_id": "gpt-5-3-codex", "benchmark_id": "aa_intelligence", "value": 54.0, "raw_value": "54"},
    {"model_id": "claude-opus-4-6", "benchmark_id": "aa_intelligence", "value": 53.0, "raw_value": "53"},
    {"model_id": "claude-sonnet-4-6", "benchmark_id": "aa_intelligence", "value": 52.0, "raw_value": "52"},
    {"model_id": "glm-5", "benchmark_id": "aa_intelligence", "value": 50.0, "raw_value": "50"},
    {"model_id": "gemini-3-1-pro", "benchmark_id": "gpqa_diamond", "value": 94.1, "raw_value": "94.1%"},
    {"model_id": "gpt-5-4", "benchmark_id": "gpqa_diamond", "value": 92.0, "raw_value": "92.0%"},
    {"model_id": "gpt-5-3-codex", "benchmark_id": "gpqa_diamond", "value": 91.5, "raw_value": "91.5%"},
    {
        "model_id": "claude-opus-4-6",
        "benchmark_id": "gpqa_diamond",
        "value": 91.3,
        "raw_value": "~91.3%",
        "source_type": "secondary",
        "verified": 0,
        "notes": "From aggregator - verify against primary",
    },
    {"model_id": "o4-mini-high", "benchmark_id": "mmmu", "value": 79.2, "raw_value": "79.2%"},
    {"model_id": "gpt-5-4", "benchmark_id": "mmmu", "value": 79.1, "raw_value": "79.1%"},
    {
        "model_id": "claude-opus-4-6",
        "benchmark_id": "swebench_verified",
        "value": 80.8,
        "raw_value": "80.8%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "gemini-3-1-pro",
        "benchmark_id": "swebench_verified",
        "value": 80.6,
        "raw_value": "80.6%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "claude-sonnet-4-6",
        "benchmark_id": "swebench_verified",
        "value": 79.6,
        "raw_value": "79.6%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "glm-5",
        "benchmark_id": "swebench_verified",
        "value": 77.8,
        "raw_value": "77.8%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "gemini-3-1-pro",
        "benchmark_id": "terminal_bench",
        "value": 78.4,
        "raw_value": "78.4%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "gpt-5-3-codex",
        "benchmark_id": "terminal_bench",
        "value": 77.3,
        "raw_value": "77.3%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "claude-opus-4-6",
        "benchmark_id": "terminal_bench",
        "value": 74.7,
        "raw_value": "74.7%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "glm-5",
        "benchmark_id": "ifeval",
        "value": 88.0,
        "raw_value": "88.0%",
        "source_type": "secondary",
        "verified": 0,
    },
    {
        "model_id": "glm-5",
        "benchmark_id": "chatbot_arena",
        "value": 1451.0,
        "raw_value": "1451",
        "source_type": "secondary",
        "verified": 0,
    },
    {"model_id": "mercury-2", "benchmark_id": "aa_speed", "value": 789.2, "raw_value": "789.2 t/s"},
    {"model_id": "gemini-2-5-flash", "benchmark_id": "aa_speed", "value": 386.1, "raw_value": "386.1 t/s"},
    {"model_id": "gemma-3n-e4b", "benchmark_id": "aa_cost", "value": 0.03, "raw_value": "$0.03/1M"},
]


def _has_rows(conn: Connection, table) -> bool:
    count = conn.execute(select(func.count()).select_from(table)).scalar_one()
    return bool(count)


def _upsert_rows(conn: Connection, table, rows: Iterable[Mapping[str, Any]]) -> None:
    stmt = sqlite_insert(table).values(list(rows))
    stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
    conn.execute(stmt)


def seed_reference_data(target: Connection | Engine, *, include_seed_scores: bool = False) -> None:
    if isinstance(target, Engine):
        with target.begin() as conn:
            seed_reference_data(conn, include_seed_scores=include_seed_scores)
        return

    conn = target
    _upsert_rows(conn, benchmarks, BENCHMARKS)
    _upsert_rows(conn, models, MODELS)

    if include_seed_scores and not _has_rows(conn, scores):
        collected_at = "2026-03-31T00:00:00Z"
        rows = []
        for row in SEED_SCORES:
            payload = dict(row)
            payload.setdefault("source_type", "primary")
            payload.setdefault("verified", 1)
            payload.setdefault("source_url", None)
            payload.setdefault("notes", None)
            payload.setdefault("collected_at", collected_at)
            rows.append(payload)
        conn.execute(scores.insert(), rows)


__all__ = [
    "AILUMINATE_GRADE_TO_SCORE",
    "BENCHMARKS",
    "MODELS",
    "SEED_SCORES",
    "USE_CASES",
    "seed_reference_data",
]
