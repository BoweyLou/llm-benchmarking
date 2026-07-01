from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup


HUGGINGFACE_MODEL_CARD_URL_TEMPLATE = "https://huggingface.co/{repo_id}"
MODEL_CARD_SUMMARY_MAX_LENGTH = 360
MARKDOWN_HTML_LINK_RE = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.S)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
README_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.S)
TRAINING_CUTOFF_RE = re.compile(
    r"\b(?:knowledge|training)(?:\s+data)?\s+cutoff\b[^:\n]*[:\-]?\s*([^\n.]{3,120})",
    re.IGNORECASE,
)


def build_huggingface_model_card_values(
    info: dict[str, Any],
    readme_text: str,
    *,
    repo_id: str,
    verified_at: str,
) -> dict[str, Any]:
    card_data = info.get("cardData") if isinstance(info.get("cardData"), dict) else {}
    frontmatter_license = extract_readme_frontmatter_value(readme_text, "license")
    readme_license_id, readme_license_name, readme_license_url = extract_license_metadata_from_readme(readme_text)
    readme_body = strip_readme_frontmatter(readme_text)
    documentation_url, repo_url, paper_url = extract_huggingface_external_urls(readme_body)
    paper_url = paper_url or extract_arxiv_paper_url(info.get("tags"))
    base_models = extract_huggingface_base_models(card_data, info.get("tags"))
    supported_languages = normalize_string_list(card_data.get("language"))
    capabilities = derive_huggingface_capabilities(info, card_data)
    intended_use = extract_markdown_section_summary(
        readme_body,
        heading_keywords=(
            "intended use",
            "recommended use",
            "use cases",
            "uses",
            "how to use",
            "usage",
        ),
    ) or extract_markdown_intro_summary(readme_body)
    limitations = extract_markdown_section_summary(
        readme_body,
        heading_keywords=(
            "limitations",
            "limitation",
            "risks",
            "risk",
            "bias",
            "biases",
            "safety",
            "out of scope",
            "out-of-scope",
        ),
    )
    training_data_summary = extract_markdown_section_summary(
        readme_body,
        heading_keywords=(
            "training data",
            "training dataset",
            "datasets",
            "data",
        ),
    )
    training_cutoff = extract_training_cutoff(readme_body)
    license_id = (
        clean_text(card_data.get("license"))
        or clean_text(info.get("license"))
        or frontmatter_license
        or readme_license_id
        or extract_huggingface_license_tag(info.get("tags"))
    )
    license_name = clean_text(card_data.get("license_name")) or readme_license_name or license_id
    license_url = clean_text(card_data.get("license_link")) or readme_license_url

    values: dict[str, Any] = {
        "huggingface_repo_id": repo_id,
        "model_card_url": HUGGINGFACE_MODEL_CARD_URL_TEMPLATE.format(repo_id=repo_id),
        "model_card_source": "huggingface",
        "model_card_verified_at": verified_at,
    }
    if documentation_url:
        values["documentation_url"] = documentation_url
    if repo_url:
        values["repo_url"] = repo_url
    if paper_url:
        values["paper_url"] = paper_url
    if license_id:
        values["license_id"] = license_id
    if license_name:
        values["license_name"] = license_name
    if license_url:
        values["license_url"] = license_url
    if base_models:
        values["base_models_json"] = json.dumps(base_models, ensure_ascii=True)
    if supported_languages:
        values["supported_languages_json"] = json.dumps(supported_languages, ensure_ascii=True)
    if capabilities:
        values["capabilities_json"] = json.dumps(capabilities, ensure_ascii=True)
    if intended_use:
        values["intended_use_short"] = intended_use
    if limitations:
        values["limitations_short"] = limitations
    if training_data_summary:
        values["training_data_summary"] = training_data_summary
    if training_cutoff:
        values["training_cutoff"] = training_cutoff
    return values


def extract_huggingface_external_urls(readme_text: str) -> tuple[str | None, str | None, str | None]:
    documentation_url: str | None = None
    repo_url: str | None = None
    paper_url: str | None = None

    for label, url in extract_markdown_links(readme_text):
        normalized_label = label.lower()
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if documentation_url is None and (
            "doc" in normalized_label
            or "guide" in normalized_label
            or "api" in normalized_label
            or "/docs" in parsed.path
        ):
            documentation_url = url
            continue
        if repo_url is None and (
            "github" in normalized_label
            or "gitlab" in normalized_label
            or "repo" in normalized_label
            or hostname in {"github.com", "gitlab.com"}
        ):
            repo_url = url
            continue
        if paper_url is None and (
            "paper" in normalized_label
            or "arxiv" in normalized_label
            or hostname in {"arxiv.org", "doi.org"}
        ):
            paper_url = url
    return documentation_url, repo_url, paper_url


def extract_huggingface_license_tag(tags: Any) -> str | None:
    for tag in tags if isinstance(tags, list) else []:
        text = str(tag or "").strip()
        if not text.lower().startswith("license:"):
            continue
        value = text.split(":", 1)[1].strip()
        if value:
            return value
    return None


def extract_readme_frontmatter_value(readme_text: str, key: str) -> str | None:
    text = str(readme_text or "")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return None
    pattern = re.compile(rf"(?m)^{re.escape(key)}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    value_match = pattern.search(match.group(1))
    if not value_match:
        return None
    return clean_text(value_match.group(1))


def extract_license_metadata_from_readme(readme_text: str) -> tuple[str | None, str | None, str | None]:
    text = str(readme_text or "")
    model_license_link = re.search(
        r"https?://huggingface\.co/[^\"'\s)]+/blob/main/LICENSE-MODEL\b",
        text,
        re.IGNORECASE,
    )
    if model_license_link:
        return "model-agreement", "Model Agreement", model_license_link.group(0)

    for label, url in extract_markdown_links(text):
        normalized_label = label.lower()
        normalized_url = url.lower()
        if "license-model" in normalized_url or "model license" in normalized_label:
            return "model-agreement", "Model Agreement", url
        if "license" in normalized_label or "/license" in normalized_url:
            return None, "License file", url
    return None, None, None


def extract_markdown_links(text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pattern in (MARKDOWN_HTML_LINK_RE, MARKDOWN_LINK_RE):
        for match in pattern.findall(text or ""):
            url, label = match if pattern is MARKDOWN_HTML_LINK_RE else (match[1], match[0])
            cleaned_url = clean_text(url)
            cleaned_label = strip_markup_to_text(label)
            if not cleaned_url or cleaned_url in seen:
                continue
            seen.add(cleaned_url)
            links.append((cleaned_label or cleaned_url, cleaned_url))
    return links


def extract_arxiv_paper_url(tags: Any) -> str | None:
    for tag in tags if isinstance(tags, list) else []:
        text = str(tag or "").strip()
        if not text.lower().startswith("arxiv:"):
            continue
        arxiv_id = text.split(":", 1)[1].strip()
        if arxiv_id:
            return f"https://arxiv.org/abs/{arxiv_id}"
    return None


def extract_huggingface_base_models(card_data: dict[str, Any], tags: Any) -> list[str]:
    base_models = normalize_string_list(card_data.get("base_model"))
    if base_models:
        return base_models

    values: list[str] = []
    for tag in tags if isinstance(tags, list) else []:
        text = str(tag or "").strip()
        if not text.lower().startswith("base_model:"):
            continue
        candidate = text.split(":", 1)[1].strip()
        if candidate.startswith("finetune:"):
            candidate = candidate.split(":", 1)[1].strip()
        if candidate:
            values.append(candidate)
    return merge_string_lists(values)


def derive_huggingface_capabilities(info: dict[str, Any], card_data: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for candidate in (
        card_data.get("pipeline_tag"),
        info.get("pipeline_tag"),
    ):
        text = clean_text(candidate)
        if text:
            values.append(text)

    useful_tags = {
        "chat",
        "conversational",
        "reasoning",
        "image-text-to-text",
        "visual-question-answering",
        "text-generation",
        "text2text-generation",
        "text-to-image",
        "text-to-video",
        "automatic-speech-recognition",
        "text-to-speech",
        "audio-text-to-text",
    }
    for tag in info.get("tags") if isinstance(info.get("tags"), list) else []:
        text = str(tag or "").strip()
        if text.lower() in useful_tags:
            values.append(text)
    return merge_string_lists(values)


def extract_markdown_section_summary(readme_text: str, *, heading_keywords: tuple[str, ...]) -> str | None:
    for heading, content in iter_markdown_sections(readme_text):
        normalized_heading = heading.lower()
        if not any(keyword in normalized_heading for keyword in heading_keywords):
            continue
        summary = shorten_summary(strip_markup_to_text(content))
        if summary:
            return summary
    return None


def extract_markdown_intro_summary(readme_text: str) -> str | None:
    text = clean_text(readme_text)
    if not text:
        return None
    body = MARKDOWN_HEADING_RE.split(readme_text, maxsplit=1)[0]
    summary = shorten_summary(strip_markup_to_text(body))
    return summary


def extract_training_cutoff(readme_text: str) -> str | None:
    match = TRAINING_CUTOFF_RE.search(readme_text or "")
    if not match:
        return None
    return shorten_summary(strip_markup_to_text(match.group(1)), limit=120)


def strip_readme_frontmatter(text: str) -> str:
    cleaned = str(text or "")
    return README_FRONTMATTER_RE.sub("", cleaned, count=1)


def iter_markdown_sections(text: str) -> Iterable[tuple[str, str]]:
    cleaned = str(text or "")
    matches = list(MARKDOWN_HEADING_RE.finditer(cleaned))
    if not matches:
        if cleaned.strip():
            yield "", cleaned
        return

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        heading = strip_markup_to_text(match.group(2))
        content = cleaned[start:end].strip()
        if content:
            yield heading, content


def strip_markup_to_text(text: Any) -> str:
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return ""
    if re.fullmatch(r"https?://\S+", stripped, re.IGNORECASE):
        return stripped
    if "<" not in stripped and ">" not in stripped and "&" not in stripped:
        html_stripped = stripped
    else:
        soup = BeautifulSoup(raw, "html.parser")
        html_stripped = soup.get_text(" ", strip=True)
    markdown_stripped = re.sub(r"`([^`]+)`", r"\1", html_stripped)
    markdown_stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", markdown_stripped)
    markdown_stripped = re.sub(r"\*([^*]+)\*", r"\1", markdown_stripped)
    markdown_stripped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", markdown_stripped)
    markdown_stripped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", markdown_stripped)
    markdown_stripped = re.sub(r"^>\s*", "", markdown_stripped, flags=re.M)
    markdown_stripped = re.sub(r"\s+", " ", markdown_stripped)
    return markdown_stripped.strip()


def shorten_summary(text: Any, *, limit: int = MODEL_CARD_SUMMARY_MAX_LENGTH) -> str | None:
    cleaned = clean_text(text)
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.")
    return f"{trimmed}..."


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [str(item) for item in value]
    else:
        values = [str(value)]
    return merge_string_lists(values)


def merge_string_lists(*lists: list[str] | None) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for values in lists:
        for item in values or []:
            cleaned = clean_text(item)
            if not cleaned:
                continue
            normalized = cleaned.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(cleaned)
    return merged


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
