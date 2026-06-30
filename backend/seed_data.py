"""Seed data and idempotent bootstrap helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Connection, Engine

from .database import benchmarks, models, providers, scores, utc_now_iso

PROVIDER_ORIGIN_VERIFIED_AT = "2026-04-02T00:00:00Z"
PROVIDER_ORIGIN_BASELINE_PATH = Path(__file__).with_name("provider_origin_baseline.json")
INTERNAL_VIEW_BENCHMARK_ID = "internal_view"


def provider_id_from_name(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return normalized or "unknown-provider"


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def normalize_origin_countries(
    raw_countries: Iterable[Mapping[str, Any]] | None,
    fallback_country_code: str | None = None,
    fallback_country_name: str | None = None,
) -> list[dict[str, str | None]]:
    normalized: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str]] = set()

    for item in raw_countries or []:
        raw_code = _clean_optional_text(item.get("code"))
        raw_name = _clean_optional_text(item.get("name"))
        if raw_code is not None:
            raw_code = raw_code.upper()
            if len(raw_code) != 2 or not raw_code.isalpha():
                raise ValueError(f"Invalid provider origin country code: {raw_code}")
        if raw_name is None and raw_code is not None:
            raw_name = raw_code
        if raw_name is None:
            continue
        key = (raw_code, raw_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"code": raw_code, "name": raw_name})

    if normalized:
        return normalized

    raw_code = _clean_optional_text(fallback_country_code)
    raw_name = _clean_optional_text(fallback_country_name)
    if raw_code is not None:
        raw_code = raw_code.upper()
        if len(raw_code) != 2 or not raw_code.isalpha():
            raise ValueError(f"Invalid provider origin country code: {raw_code}")
    if raw_name is None and raw_code is not None:
        raw_name = raw_code
    if raw_name is None:
        return []
    return [{"code": raw_code, "name": raw_name}]


def derive_provider_origin_fields(origin_countries: Iterable[Mapping[str, Any]] | None) -> tuple[str | None, str | None]:
    countries = normalize_origin_countries(origin_countries)
    if not countries:
        return None, None
    if len(countries) == 1:
        return countries[0].get("code"), countries[0].get("name")
    names = [str(country.get("name") or "").strip() for country in countries if str(country.get("name") or "").strip()]
    return None, ", ".join(dict.fromkeys(names)) or None


def load_provider_origin_baseline(path: Path | None = None) -> list[dict[str, Any]]:
    baseline_path = path or PROVIDER_ORIGIN_BASELINE_PATH
    if not baseline_path.exists():
        return []

    raw_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, list):
        raise ValueError("Provider origin baseline must be a JSON array.")

    normalized_payload: list[dict[str, Any]] = []
    for item in raw_payload:
        if not isinstance(item, Mapping):
            continue
        provider_id = _clean_optional_text(item.get("id"))
        provider_name = _clean_optional_text(item.get("name"))
        if provider_id is None or provider_name is None:
            continue
        origin_countries = normalize_origin_countries(
            item.get("origin_countries"),
            _clean_optional_text(item.get("country_code")),
            _clean_optional_text(item.get("country_name")),
        )
        country_code, country_name = derive_provider_origin_fields(origin_countries)
        normalized_payload.append(
            {
                "id": provider_id,
                "name": provider_name,
                "country_code": country_code,
                "country_name": country_name,
                "origin_countries_json": json.dumps(origin_countries, separators=(",", ":")),
                "origin_basis": _clean_optional_text(item.get("origin_basis")),
                "source_url": _clean_optional_text(item.get("source_url")),
                "verified_at": _clean_optional_text(item.get("verified_at")),
                "active": 1 if item.get("active", True) else 0,
            }
        )

    return normalized_payload


def apply_provider_origin_baseline(target: Connection | Engine) -> int:
    if isinstance(target, Engine):
        with target.begin() as conn:
            return apply_provider_origin_baseline(conn)

    rows = load_provider_origin_baseline()
    if not rows:
        return 0

    stmt = sqlite_insert(providers).values(rows)
    update_columns = {
        column.name: getattr(stmt.excluded, column.name)
        for column in providers.columns
        if column.name != "id"
    }
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_columns)
    target.execute(stmt)
    return len(rows)


def export_provider_origin_baseline(target: Connection | Engine, path: Path | None = None) -> Path:
    baseline_path = path or PROVIDER_ORIGIN_BASELINE_PATH
    if isinstance(target, Engine):
        with target.begin() as conn:
            return export_provider_origin_baseline(conn, baseline_path)

    rows = (
        target.execute(select(providers).where(providers.c.active == 1).order_by(providers.c.name.asc()))
        .mappings()
        .all()
    )
    payload: list[dict[str, Any]] = []
    for row in rows:
        origin_countries = normalize_origin_countries(
            json.loads(str(row.get("origin_countries_json") or "[]")),
            row.get("country_code"),
            row.get("country_name"),
        )
        payload.append(
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "origin_countries": origin_countries,
                "origin_basis": _clean_optional_text(row.get("origin_basis")),
                "source_url": _clean_optional_text(row.get("source_url")),
                "verified_at": _clean_optional_text(row.get("verified_at")),
                "active": bool(row.get("active", 1)),
            }
        )

    baseline_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return baseline_path

BENCHMARKS: list[dict[str, Any]] = [
    {
        "id": INTERNAL_VIEW_BENCHMARK_ID,
        "name": "Internal View",
        "short": "Internal",
        "source": "Internal",
        "url": "",
        "category": "Internal Assessment",
        "metric": "Internal Score",
        "higher_is_better": 1,
        "tier": 2,
        "scraper_id": "InternalManualBenchmark",
        "description": "Optional internal assessment signal entered manually to reflect business context, rollout preferences, or operator experience.",
        "active": 1,
    },
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
        "tier": 1,
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
        "tier": 3,
        "scraper_id": "MmmuAdapter",
        "description": "Useful academic multimodal signal, but the public leaderboard updates slowly and this ingestion uses the validation split rather than a fresh held-out test feed.",
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
        "tier": 2,
        "scraper_id": "SwebenchAdapter",
        "description": "Derived from the official SWE-bench Verified board using the best single-model system submission per model. Strong coding evidence, but still agent-derived rather than a pure model-only eval.",
        "active": 1,
    },
    {
        "id": "ifeval",
        "name": "IFEval",
        "short": "IFEval",
        "source": "LLM Stats / ZeroEval",
        "url": "https://llm-stats.com/benchmarks/ifeval",
        "category": "Instruction Following",
        "metric": "Prompt Accuracy %",
        "higher_is_better": 1,
        "tier": 3,
        "scraper_id": "IfevalAdapter",
        "description": "Instruction-following signal pulled from a live feed that is currently overwhelmingly self-reported and unverified. Useful context, but lower-trust than primary benchmark publishers.",
        "active": 1,
    },
    {
        "id": "rag_groundedness",
        "name": "Vectara Hallucination Leaderboard",
        "short": "Vectara FC",
        "source": "Vectara",
        "url": "https://github.com/vectara/hallucination-leaderboard",
        "category": "Retrieval & Grounding",
        "metric": "Factual Consistency %",
        "higher_is_better": 1,
        "tier": 3,
        "scraper_id": "VectaraHallucinationAdapter",
        "description": "Grounded summarization faithfulness to supplied source text. Useful directional evidence, but narrower than end-to-end retrieval relevance or enterprise RAG quality.",
        "active": 1,
    },
    {
        "id": "rag_task_faithfulness",
        "name": "FaithJudge",
        "short": "FaithJudge",
        "source": "Vectara",
        "url": "https://github.com/vectara/FaithJudge#leaderboard",
        "category": "Retrieval & Grounding",
        "metric": "Hallucination Rate %",
        "higher_is_better": 0,
        "tier": 3,
        "scraper_id": "FaithJudgeAdapter",
        "description": "Small vendor-run hallucination benchmark across FaithBench and RagTruth tasks with supplied context. Useful directional signal, but coverage is narrow and not a retrieval relevance eval.",
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
        "tier": 2,
        "scraper_id": "AILuminateAdapter",
        "description": "Official MLCommons safety benchmark, but the public named results are coarse grade bands and mix bare models with broader AI systems.",
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

PROVIDERS: list[dict[str, Any]] = [
    {
        "id": provider_id_from_name("OpenAI"),
        "name": "OpenAI",
        "country_code": "US",
        "country_name": "United States",
        "origin_basis": "Official OpenAI document listing San Francisco, California.",
        "source_url": "https://cdn.openai.com/global-affairs/openai-doe-rfi-5-7-2025.pdf",
        "verified_at": PROVIDER_ORIGIN_VERIFIED_AT,
        "active": 1,
    },
    {
        "id": provider_id_from_name("Anthropic"),
        "name": "Anthropic",
        "country_code": "US",
        "country_name": "United States",
        "origin_basis": "Official Anthropic privacy notice listing San Francisco, California.",
        "source_url": "https://www-cdn.anthropic.com/8fd65f023a39d74220c5ebff85c788875c05533f.pdf",
        "verified_at": PROVIDER_ORIGIN_VERIFIED_AT,
        "active": 1,
    },
    {
        "id": provider_id_from_name("Google"),
        "name": "Google",
        "country_code": "US",
        "country_name": "United States",
        "origin_basis": "Official Google company information and locations pages.",
        "source_url": "https://about.google/company-info/locations/",
        "verified_at": PROVIDER_ORIGIN_VERIFIED_AT,
        "active": 1,
    },
    {
        "id": provider_id_from_name("Inception Labs"),
        "name": "Inception Labs",
        "country_code": "US",
        "country_name": "United States",
        "origin_basis": "Official Inception Labs legal documentation for the company.",
        "source_url": "https://www.inceptionlabs.ai/docs/terms-of-use",
        "verified_at": PROVIDER_ORIGIN_VERIFIED_AT,
        "active": 1,
    },
    {
        "id": provider_id_from_name("Zhipu AI"),
        "name": "Zhipu AI",
        "country_code": "CN",
        "country_name": "China",
        "origin_basis": "Official Zhipu agreement naming the Beijing legal entity.",
        "source_url": "https://docs.bigmodel.cn/cn/terms/recharge-agreement",
        "verified_at": PROVIDER_ORIGIN_VERIFIED_AT,
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
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": ["gpqa_diamond"],
        "benchmark_notes": {
            "gpqa_diamond": "Hard factual reasoning and exam-style problem solving.",
            "chatbot_arena": "User-facing helpfulness and response quality context.",
            "aa_intelligence": "Broad capability proxy for general model strength.",
        },
        "weights": {"aa_intelligence": 0.40, "gpqa_diamond": 0.35, "chatbot_arena": 0.25},
    },
    {
        "id": "coding",
        "label": "Coding & Engineering",
        "icon": "💻",
        "description": "Code generation, debugging, repo-level tasks, DevOps",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.45,
        "required_benchmarks": ["swebench_verified", "terminal_bench"],
        "benchmark_notes": {
            "swebench_verified": "Repo-level bug fixing and code-change execution.",
            "terminal_bench": "Agent-derived workflow evidence from verified single-model submissions.",
            "aa_intelligence": "General capability proxy for coding-adjacent reasoning.",
        },
        "weights": {"swebench_verified": 0.55, "aa_intelligence": 0.25, "terminal_bench": 0.20},
    },
    {
        "id": "agentic",
        "label": "Agentic & Tool Use",
        "icon": "🤖",
        "description": "Multi-step workflows, API calls, terminal and browser automation",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": ["terminal_bench", "swebench_verified"],
        "benchmark_notes": {
            "terminal_bench": "Agent-derived workflow evidence from verified single-model submissions.",
            "swebench_verified": "Tool-using repo-level execution under realistic constraints.",
            "aa_intelligence": "General capability proxy for planning and reasoning.",
        },
        "weights": {"terminal_bench": 0.50, "swebench_verified": 0.25, "aa_intelligence": 0.25},
    },
    {
        "id": "safety_compliance",
        "label": "Safety & Compliance",
        "icon": "🛡️",
        "description": "Harmful output avoidance, hazard categories, regulatory readiness",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": [],
        "benchmark_notes": {
            "ailuminate": "Low-confidence safety context from coarse public MLCommons grades.",
            "aa_intelligence": "Primary fallback capability context while safety evidence remains thin.",
        },
        "weights": {"aa_intelligence": 0.80, "ailuminate": 0.20},
    },
    {
        "id": "cost_efficiency",
        "label": "Cost Efficiency",
        "icon": "💰",
        "description": "Minimise spend while maintaining quality for high-volume use",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": ["aa_cost", "aa_speed"],
        "benchmark_notes": {
            "aa_cost": "Unit economics and spend per generated output.",
            "aa_speed": "Throughput and latency under load.",
            "aa_intelligence": "Quality context so low cost does not hide weak capability.",
        },
        "weights": {"aa_cost": 0.60, "aa_speed": 0.25, "aa_intelligence": 0.15},
    },
    {
        "id": "multimodal",
        "label": "Multimodal",
        "icon": "🖼️",
        "description": "Vision-language, chart understanding, document image processing",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": [],
        "benchmark_notes": {
            "mmmu": "Low-confidence multimodal context from a slowly updated academic leaderboard.",
            "aa_intelligence": "Primary capability anchor until stronger multimodal evidence is added.",
        },
        "weights": {"aa_intelligence": 0.85, "mmmu": 0.15},
    },
    {
        "id": "instruction_following",
        "label": "Instruction Following",
        "icon": "📋",
        "description": "Strict adherence to constraints, formatting rules, complex prompt structures",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": [],
        "benchmark_notes": {
            "ifeval": "Low-confidence context from a feed dominated by self-reported scores.",
            "chatbot_arena": "Response quality context.",
            "aa_intelligence": "Primary fallback for overall instruction-heavy task competence.",
        },
        "weights": {"aa_intelligence": 0.55, "chatbot_arena": 0.30, "ifeval": 0.15},
    },
    {
        "id": "speed",
        "label": "Speed / Latency",
        "icon": "⚡",
        "description": "Maximum throughput for real-time, streaming, or high-concurrency apps",
        "segment": "core",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": ["aa_speed"],
        "benchmark_notes": {
            "aa_speed": "Throughput and latency under production-like load.",
            "aa_intelligence": "Quality context so the fastest model is not selected blindly.",
        },
        "weights": {"aa_speed": 0.80, "aa_intelligence": 0.20},
    },
    {
        "id": "enterprise_automation",
        "label": "Enterprise Automation",
        "icon": "🏢",
        "description": "Internal copilots, workflow execution, ticket triage, and system actions under enterprise constraints",
        "segment": "enterprise",
        "status": "preview",
        "min_coverage": 0.55,
        "required_benchmarks": ["terminal_bench"],
        "benchmark_notes": {
            "terminal_bench": "Agent-derived workflow evidence from verified single-model submissions.",
            "ifeval": "Low-confidence instruction-following context only.",
            "ailuminate": "Low-confidence safety context only.",
            "aa_intelligence": "General capability context.",
            "aa_cost": "Operational spend for high-volume automation.",
            "aa_speed": "Latency for interactive workflows.",
        },
        "weights": {
            "terminal_bench": 0.50,
            "aa_intelligence": 0.25,
            "aa_cost": 0.10,
            "aa_speed": 0.05,
            "ifeval": 0.05,
            "ailuminate": 0.05,
        },
    },
    {
        "id": "customer_support",
        "label": "Customer Support",
        "icon": "🎧",
        "description": "Service desk chat, escalation handling, response quality, safety, and operating cost at scale",
        "segment": "enterprise",
        "status": "preview",
        "min_coverage": 0.5,
        "required_benchmarks": ["chatbot_arena"],
        "benchmark_notes": {
            "chatbot_arena": "Preference and conversational quality for support-style interactions.",
            "ifeval": "Low-confidence policy/format-following context only.",
            "ailuminate": "Low-confidence public safety context only.",
            "aa_cost": "Unit economics for support at scale.",
            "aa_speed": "Latency for interactive service conversations.",
        },
        "weights": {
            "chatbot_arena": 0.55,
            "aa_cost": 0.20,
            "aa_speed": 0.10,
            "ifeval": 0.10,
            "ailuminate": 0.05,
        },
    },
    {
        "id": "document_operations",
        "label": "Document Operations",
        "icon": "🗂️",
        "description": "Document review, form extraction, policy QA, and visual enterprise content workflows",
        "segment": "enterprise",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": [],
        "benchmark_notes": {
            "mmmu": "Low-confidence multimodal context for forms, charts, and screenshots.",
            "ifeval": "Low-confidence instruction-following context for extraction and policy QA.",
            "aa_intelligence": "General capability context for mixed document tasks.",
            "ailuminate": "Low-confidence safety context when document content is sensitive.",
            "aa_speed": "Throughput for bulk processing.",
        },
        "weights": {
            "aa_intelligence": 0.50,
            "aa_speed": 0.20,
            "mmmu": 0.15,
            "ailuminate": 0.10,
            "ifeval": 0.05,
        },
    },
    {
        "id": "knowledge_work_rag_sorting",
        "label": "Knowledge Work / RAG Retrieval Sorting",
        "icon": "🔎",
        "description": "Retrieval sorting, context ranking, and grounded answer shaping around retrieved context",
        "segment": "enterprise",
        "status": "preview",
        "min_coverage": 0.55,
        "required_benchmarks": [],
        "benchmark_notes": {
            "rag_groundedness": "Low-confidence groundedness context only; it is not a retrieval relevance eval.",
            "rag_task_faithfulness": "Low-confidence hallucination context only; it does not measure retrieval quality directly.",
            "ifeval": "Low-confidence instruction-following context only.",
            "aa_intelligence": "Primary capability anchor for synthesis and analysis once retrieval is assembled.",
            "chatbot_arena": "Answer quality after retrieval is assembled.",
            "gpqa_diamond": "Reasoning quality once retrieved material is available.",
        },
        "weights": {
            "aa_intelligence": 0.50,
            "chatbot_arena": 0.20,
            "gpqa_diamond": 0.20,
            "rag_task_faithfulness": 0.05,
            "rag_groundedness": 0.03,
            "ifeval": 0.02,
        },
    },
    {
        "id": "governed_enterprise_rollout",
        "label": "Governed Enterprise Rollout",
        "icon": "📜",
        "description": "Regulated deployment, procurement, and risk-sensitive rollout decisions",
        "segment": "enterprise",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": [],
        "benchmark_notes": {
            "ailuminate": "Low-confidence public safety context only.",
            "ifeval": "Low-confidence instruction-following context for policy and rollout controls.",
            "aa_intelligence": "General capability context for procurement tradeoffs.",
            "aa_cost": "Operational spend and vendor economics.",
        },
        "weights": {
            "aa_intelligence": 0.60,
            "aa_cost": 0.25,
            "ailuminate": 0.10,
            "ifeval": 0.05,
        },
    },
    {
        "id": "developer_platform_agent",
        "label": "Developer Platform Agent",
        "icon": "🧩",
        "description": "Internal engineering automation, repo tasks, and CI/CD support",
        "segment": "enterprise",
        "status": "preview",
        "min_coverage": 0.55,
        "required_benchmarks": ["terminal_bench", "swebench_verified"],
        "benchmark_notes": {
            "terminal_bench": "Agent-derived workflow evidence for terminal and tool execution.",
            "swebench_verified": "Repo-level bug fixing and code-change execution.",
            "ifeval": "Low-confidence instruction-following context for build and change-management steps.",
            "aa_intelligence": "General reasoning context for engineering workflows.",
        },
        "weights": {
            "terminal_bench": 0.40,
            "swebench_verified": 0.35,
            "aa_intelligence": 0.20,
            "ifeval": 0.05,
        },
    },
    {
        "id": "workflow_automation",
        "label": "Workflow Automation",
        "icon": "🔁",
        "description": "Back-office automation, queue handling, and multi-step ops workflows",
        "segment": "enterprise",
        "status": "preview",
        "min_coverage": 0.55,
        "required_benchmarks": ["terminal_bench"],
        "benchmark_notes": {
            "terminal_bench": "Agent-derived workflow evidence for multi-step execution.",
            "ifeval": "Low-confidence instruction-following context for operational procedures.",
            "ailuminate": "Low-confidence safety context for actions that touch business systems.",
            "aa_cost": "Operating cost for high-volume workflow execution.",
            "aa_speed": "Latency and throughput for queue-driven work.",
        },
        "weights": {
            "terminal_bench": 0.60,
            "aa_cost": 0.15,
            "aa_speed": 0.10,
            "ifeval": 0.10,
            "ailuminate": 0.05,
        },
    },
    {
        "id": "small_model_routing",
        "label": "Small-Model Routing",
        "icon": "🌱",
        "description": "When to use small, fast, and cheap models for triage and first-pass work",
        "segment": "enterprise",
        "status": "ready",
        "min_coverage": 0.5,
        "required_benchmarks": ["aa_cost", "aa_speed"],
        "benchmark_notes": {
            "aa_cost": "Primary economic signal for cheap first-pass routing.",
            "aa_speed": "Latency and throughput for triage and extraction.",
            "ifeval": "Low-confidence reliability context for formatting and routing rules.",
            "chatbot_arena": "Output quality when a small model handles first-pass work.",
            "ailuminate": "Low-confidence safety context only.",
        },
        "weights": {
            "aa_cost": 0.45,
            "aa_speed": 0.35,
            "chatbot_arena": 0.15,
            "ifeval": 0.03,
            "ailuminate": 0.02,
        },
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


def _upsert_rows(
    conn: Connection,
    table,
    rows: Iterable[Mapping[str, Any]],
    *,
    preserve_columns: Iterable[str] = (),
) -> None:
    rows_list = list(rows)
    if not rows_list:
        return

    stmt = sqlite_insert(table).values(rows_list)
    preserved = set(preserve_columns)
    update_columns = {
        column.name: getattr(stmt.excluded, column.name)
        for column in table.columns
        if column.name != "id" and column.name not in preserved
    }
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_columns)
    conn.execute(stmt)


def _insert_rows_if_missing(conn: Connection, table, rows: Iterable[Mapping[str, Any]]) -> None:
    rows_list = list(rows)
    if not rows_list:
        return

    stmt = sqlite_insert(table).values(rows_list)
    stmt = stmt.on_conflict_do_nothing(index_elements=["id"])
    conn.execute(stmt)


def seed_reference_data(target: Connection | Engine, *, include_seed_scores: bool = False) -> None:
    if isinstance(target, Engine):
        with target.begin() as conn:
            seed_reference_data(conn, include_seed_scores=include_seed_scores)
        return

    conn = target
    _upsert_rows(conn, benchmarks, BENCHMARKS)
    _insert_rows_if_missing(conn, providers, PROVIDERS)
    apply_provider_origin_baseline(conn)
    _upsert_rows(
        conn,
        models,
        [
            {
                **row,
                "provider_id": row.get("provider_id") or provider_id_from_name(str(row.get("provider") or "")),
            }
            for row in MODELS
        ],
        preserve_columns=("approved_for_use", "approval_notes", "approval_updated_at"),
    )

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
    "INTERNAL_VIEW_BENCHMARK_ID",
    "MODELS",
    "PROVIDERS",
    "PROVIDER_ORIGIN_BASELINE_PATH",
    "SEED_SCORES",
    "USE_CASES",
    "apply_provider_origin_baseline",
    "derive_provider_origin_fields",
    "export_provider_origin_baseline",
    "load_provider_origin_baseline",
    "normalize_origin_countries",
    "provider_id_from_name",
    "seed_reference_data",
]
