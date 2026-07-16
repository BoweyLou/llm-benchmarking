"""Provider API catalog adapters for authenticated model discovery.

The functions in this module intentionally stop at fetching and normalizing
provider model-list payloads. Database writes stay in ``update_engine``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any
from urllib.parse import urljoin

import httpx


CatalogModel = dict[str, Any]
Parser = Callable[[Any], list[CatalogModel]]
NextPageToken = Callable[[Any], str | None]

MODEL_ROLE_GENERATOR = "generator"
MODEL_ROLE_EMBEDDING = "embedding"
MODEL_ROLE_RERANKER = "reranker"
MODEL_ROLE_MULTIMODAL_EMBEDDING = "multimodal_embedding"
MODEL_ROLE_DOCUMENT_LAYOUT = "document_layout"
MODEL_ROLE_DOCUMENT_PARSING = "document_parsing"
MODEL_ROLE_OCR = "ocr"
MODEL_ROLE_CONTENT_SAFETY = "content_safety"
MODEL_ROLE_SPEECH_TO_TEXT = "speech_to_text"
MODEL_ROLE_TEXT_TO_SPEECH = "text_to_speech"
VALID_MODEL_ROLES = {
    MODEL_ROLE_GENERATOR,
    MODEL_ROLE_EMBEDDING,
    MODEL_ROLE_RERANKER,
    MODEL_ROLE_MULTIMODAL_EMBEDDING,
    MODEL_ROLE_DOCUMENT_LAYOUT,
    MODEL_ROLE_DOCUMENT_PARSING,
    MODEL_ROLE_OCR,
    MODEL_ROLE_CONTENT_SAFETY,
    MODEL_ROLE_SPEECH_TO_TEXT,
    MODEL_ROLE_TEXT_TO_SPEECH,
}
ROLE_ORDER = {
    MODEL_ROLE_EMBEDDING: 0,
    MODEL_ROLE_GENERATOR: 1,
    MODEL_ROLE_MULTIMODAL_EMBEDDING: 2,
    MODEL_ROLE_RERANKER: 3,
    MODEL_ROLE_DOCUMENT_LAYOUT: 4,
    MODEL_ROLE_DOCUMENT_PARSING: 5,
    MODEL_ROLE_OCR: 6,
    MODEL_ROLE_CONTENT_SAFETY: 7,
    MODEL_ROLE_SPEECH_TO_TEXT: 8,
    MODEL_ROLE_TEXT_TO_SPEECH: 9,
}

PROVIDER_API_MODEL_DISCOVERY_SOURCE_NAME = "provider_api_model_discovery"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; LLMBenchmarkingBot/0.1; +https://localhost)",
}

_DATE_RE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?|-Q[1-4])?$")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


class ProviderCatalogError(RuntimeError):
    """Base error for provider catalog helpers."""


class ProviderCatalogNotConfigured(ProviderCatalogError):
    """Raised when an adapter cannot run without configured credentials."""


def safe_provider_catalog_error(
    error: Exception,
    catalog: ProviderCatalogAdapter | Mapping[str, Any] | str,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return a bounded diagnostic with credentials and URL query values removed."""

    adapter = _coerce_adapter(catalog)
    env_values = env or os.environ
    message = str(error)
    for group in adapter.env_var_groups:
        for name in group:
            secret = str(env_values.get(name) or "").strip()
            if secret:
                message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"([?&][^=\s&]+)=([^&\s]+)", r"\1[REDACTED]", message)
    return message[:1000]


@dataclass(frozen=True)
class ProviderCatalogAdapter:
    """Metadata and fetch instructions for one provider model-list API."""

    id: str
    family: str
    provider: str
    base_url: str
    list_path: str
    documentation_url: str
    source_url: str
    env_var_groups: tuple[tuple[str, ...], ...]
    auth_scheme: str
    parser: Parser
    model_roles: tuple[str, ...] = (MODEL_ROLE_GENERATOR,)
    model_type: str = "proprietary"
    default_params: tuple[tuple[str, str], ...] = ()
    page_size_param: str | None = None
    page_token_param: str | None = None
    default_page_size: int | None = None
    max_pages: int = 20
    next_page_token: NextPageToken | None = None

    @property
    def list_url(self) -> str:
        return urljoin(self.base_url.rstrip("/") + "/", self.list_path.lstrip("/"))

    def metadata(self) -> dict[str, Any]:
        """Return serializable adapter metadata without parser callables."""

        return {
            "id": self.id,
            "family": self.family,
            "provider": self.provider,
            "base_url": self.base_url,
            "list_path": self.list_path,
            "list_url": self.list_url,
            "documentation_url": self.documentation_url,
            "source_url": self.source_url,
            "env_var_groups": [list(group) for group in self.env_var_groups],
            "auth_scheme": self.auth_scheme,
            "model_roles": list(self.model_roles),
            "model_type": self.model_type,
            "default_params": dict(self.default_params),
            "page_size_param": self.page_size_param,
            "page_token_param": self.page_token_param,
            "default_page_size": self.default_page_size,
            "max_pages": self.max_pages,
            "paginated": self.next_page_token is not None,
        }


def provider_api_catalogs(*, family: str | None = None) -> list[ProviderCatalogAdapter]:
    """Return configured provider API catalog adapters, optionally filtered."""

    family_filter = _key(family)
    adapters = list(PROVIDER_CATALOG_ADAPTERS)
    if not family_filter:
        return adapters
    return [
        adapter
        for adapter in adapters
        if family_filter in {_key(adapter.id), _key(adapter.family), _key(adapter.provider)}
    ]


def list_provider_catalog_adapters(*, family: str | None = None) -> list[dict[str, Any]]:
    """Return serializable adapter metadata for discovery and UI surfaces."""

    return [adapter.metadata() for adapter in provider_api_catalogs(family=family)]


def get_provider_catalog_adapter(provider_id: str) -> ProviderCatalogAdapter:
    """Look up an adapter by id, family, or provider name."""

    requested = _key(provider_id)
    for adapter in PROVIDER_CATALOG_ADAPTERS:
        if requested in {_key(adapter.id), _key(adapter.family), _key(adapter.provider)}:
            return adapter
    raise KeyError(f"Unknown provider catalog adapter: {provider_id}")


def provider_catalog_env_requirements(*, family: str | None = None) -> dict[str, list[list[str]]]:
    """Return environment-variable alternatives required by each adapter."""

    return {
        adapter.id: [list(group) for group in adapter.env_var_groups]
        for adapter in provider_api_catalogs(family=family)
    }


def missing_provider_catalog_env_vars(
    adapter_or_id: ProviderCatalogAdapter | str,
    *,
    env: Mapping[str, str] | None = None,
) -> list[tuple[str, ...]]:
    """Return required env-var groups for which no variable is configured."""

    adapter = _coerce_adapter(adapter_or_id)
    env_values = env or os.environ
    missing: list[tuple[str, ...]] = []
    for group in adapter.env_var_groups:
        if not any(str(env_values.get(name) or "").strip() for name in group):
            missing.append(group)
    return missing


def fetch_provider_api_catalog_payloads(
    client: httpx.Client,
    catalog: ProviderCatalogAdapter | Mapping[str, Any] | str,
    *,
    env: Mapping[str, str] | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
) -> list[Any]:
    """Fetch raw model-list pages for a provider using an ``httpx.Client``."""

    adapter = _coerce_adapter(catalog)
    env_values = env or os.environ
    _require_credentials(adapter, env_values)

    headers = _auth_headers(adapter, env_values)
    params: dict[str, Any] = dict(adapter.default_params)
    if adapter.auth_scheme == "google_api_key":
        params["key"] = _credential_value(adapter, env_values)
    if adapter.page_size_param and (page_size or adapter.default_page_size):
        params[adapter.page_size_param] = page_size or adapter.default_page_size

    pages: list[Any] = []
    page_token: str | None = None
    page_limit = max_pages if max_pages is not None else adapter.max_pages
    for _ in range(max(1, page_limit)):
        request_params = dict(params)
        if page_token and adapter.page_token_param:
            request_params[adapter.page_token_param] = page_token
        response = client.get(adapter.list_url, headers=headers, params=request_params or None)
        response.raise_for_status()
        payload = response.json()
        pages.append(payload)
        if adapter.next_page_token is None:
            break
        page_token = adapter.next_page_token(payload)
        if not page_token:
            break
    return pages


def fetch_provider_api_catalog_models(
    client: httpx.Client,
    catalog: ProviderCatalogAdapter | Mapping[str, Any] | str,
    *,
    env: Mapping[str, str] | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
) -> list[CatalogModel]:
    """Fetch and normalize provider API models into catalog-model dicts."""

    adapter = _coerce_adapter(catalog)
    payloads = fetch_provider_api_catalog_payloads(
        client,
        adapter,
        env=env,
        page_size=page_size,
        max_pages=max_pages,
    )
    models: list[CatalogModel] = []
    for payload in payloads:
        models.extend(adapter.parser(payload))
    return _dedupe_models(models)


def parse_provider_api_catalog_models(provider_id: str, payload: Any) -> list[CatalogModel]:
    """Normalize one raw provider payload without performing network I/O."""

    return get_provider_catalog_adapter(provider_id).parser(payload)


def parse_openai_models(payload: Any) -> list[CatalogModel]:
    models: list[CatalogModel] = []
    for item in _payload_items(payload, "data"):
        remote_id = _clean_text(item.get("id"))
        if not remote_id:
            continue
        roles = _infer_roles(
            remote_id,
            item.get("object"),
            item.get("owned_by"),
        )
        capabilities = _capabilities_from_values(
            roles=roles,
            text_values=(remote_id, item.get("object"), item.get("owned_by")),
        )
        models.append(
            _catalog_model(
                provider_slug="openai",
                provider_name="OpenAI",
                remote_id=remote_id,
                name=_clean_text(item.get("display_name")) or remote_id,
                source_url=OPENAI_MODELS_API_URL,
                documentation_url=OPENAI_MODELS_DOC_URL,
                model_roles=roles,
                capabilities=capabilities,
                raw=item,
            )
        )
    return _dedupe_models(models)


def parse_anthropic_models(payload: Any) -> list[CatalogModel]:
    models: list[CatalogModel] = []
    for item in _payload_items(payload, "data"):
        remote_id = _clean_text(item.get("id"))
        if not remote_id:
            continue
        capability_values = _capability_values(item.get("capabilities"))
        roles = _infer_roles(
            remote_id,
            item.get("display_name"),
            item.get("name"),
            capability_values=capability_values,
            default=(MODEL_ROLE_GENERATOR,),
        )
        models.append(
            _catalog_model(
                provider_slug="anthropic",
                provider_name="Anthropic",
                remote_id=remote_id,
                name=_clean_text(item.get("display_name")) or _clean_text(item.get("name")) or remote_id,
                source_url=ANTHROPIC_MODELS_API_URL,
                documentation_url=ANTHROPIC_MODELS_DOC_URL,
                model_roles=roles,
                capabilities=_capabilities_from_values(
                    roles=roles,
                    capability_values=capability_values,
                    text_values=(remote_id, item.get("display_name"), item.get("name")),
                ),
                context_window_tokens=_first_int(item, "max_input_tokens", "context_window_tokens", "context_window"),
                max_output_tokens=_first_int(item, "max_tokens", "max_output_tokens", "output_token_limit"),
                raw=item,
            )
        )
    return _dedupe_models(models)


def parse_google_gemini_models(payload: Any) -> list[CatalogModel]:
    models: list[CatalogModel] = []
    for item in _payload_items(payload, "models"):
        remote_id = _google_model_id(item)
        if not remote_id:
            continue
        methods = _string_list(item.get("supportedGenerationMethods"))
        roles = _infer_roles(
            remote_id,
            item.get("displayName"),
            item.get("description"),
            method_values=methods,
            default=(MODEL_ROLE_GENERATOR,),
        )
        models.append(
            _catalog_model(
                provider_slug="google",
                provider_name="Google",
                remote_id=remote_id,
                name=_clean_text(item.get("displayName")) or remote_id,
                source_url=GOOGLE_GEMINI_MODELS_API_URL,
                documentation_url=GOOGLE_GEMINI_MODELS_DOC_URL,
                model_roles=roles,
                capabilities=_capabilities_from_values(
                    roles=roles,
                    capability_values=[*methods, item.get("thinking")],
                    text_values=(remote_id, item.get("displayName"), item.get("description")),
                ),
                context_window_tokens=_first_int(item, "inputTokenLimit", "context_window_tokens"),
                max_output_tokens=_first_int(item, "outputTokenLimit", "max_output_tokens"),
                raw=item,
                description=_clean_text(item.get("description")),
            )
        )
    return _dedupe_models(models)


def parse_mistral_models(payload: Any) -> list[CatalogModel]:
    models: list[CatalogModel] = []
    for item in _payload_items(payload, "data"):
        remote_id = _clean_text(item.get("id"))
        if not remote_id:
            continue
        capability_values = _capability_values(item.get("capabilities"))
        roles = _infer_roles(
            remote_id,
            item.get("root"),
            capability_values=capability_values,
            default=(MODEL_ROLE_GENERATOR,),
        )
        aliases = _string_list(item.get("aliases"))
        models.append(
            _catalog_model(
                provider_slug="mistral",
                provider_name="Mistral",
                remote_id=remote_id,
                name=_clean_text(item.get("name")) or _clean_text(item.get("root")) or remote_id,
                source_url=MISTRAL_MODELS_API_URL,
                documentation_url=MISTRAL_MODELS_DOC_URL,
                model_roles=roles,
                capabilities=_capabilities_from_values(
                    roles=roles,
                    capability_values=[*capability_values, *aliases],
                    text_values=(remote_id, item.get("root"), item.get("TYPE")),
                ),
                context_window_tokens=_first_int(item, "max_context_length", "context_window_tokens"),
                max_output_tokens=_first_int(item, "max_output_tokens"),
                raw=item,
                catalog_status=_catalog_status(item),
                model_type=_clean_text(item.get("TYPE")) or None,
            )
        )
    return _dedupe_models(models)


def parse_cohere_models(payload: Any) -> list[CatalogModel]:
    models: list[CatalogModel] = []
    for item in _payload_items(payload, "models"):
        remote_id = _clean_text(item.get("name")) or _clean_text(item.get("id"))
        if not remote_id:
            continue
        endpoints = _string_list(item.get("endpoints"))
        default_endpoints = _string_list(item.get("default_endpoints"))
        features = _string_list(item.get("features"))
        roles = _infer_roles(
            remote_id,
            *endpoints,
            *features,
            method_values=[*endpoints, *default_endpoints],
            capability_values=features,
            default=(MODEL_ROLE_GENERATOR,),
        )
        models.append(
            _catalog_model(
                provider_slug="cohere",
                provider_name="Cohere",
                remote_id=remote_id,
                name=_clean_text(item.get("display_name")) or remote_id,
                source_url=COHERE_MODELS_API_URL,
                documentation_url=COHERE_MODELS_DOC_URL,
                model_roles=roles,
                capabilities=_capabilities_from_values(
                    roles=roles,
                    capability_values=[*endpoints, *default_endpoints, *features],
                    text_values=(remote_id,),
                ),
                context_window_tokens=_first_int(item, "context_length", "context_window_tokens"),
                max_output_tokens=_first_int(item, "max_output_tokens"),
                raw=item,
                catalog_status=_catalog_status(item),
                repo_url=_clean_text(item.get("tokenizer_url")) or None,
            )
        )
    return _dedupe_models(models)


def parse_xai_models(payload: Any) -> list[CatalogModel]:
    models: list[CatalogModel] = []
    for item in _payload_items(payload, "data", "models"):
        remote_id = _clean_text(item.get("id")) or _clean_text(item.get("name"))
        if not remote_id:
            continue
        modalities = _dedupe_strings(
            [
                *_string_list(item.get("modalities")),
                *_string_list(item.get("input_modalities")),
                *_string_list(item.get("output_modalities")),
            ]
        )
        aliases = _string_list(item.get("aliases"))
        roles = _infer_roles(
            remote_id,
            item.get("object"),
            *modalities,
            capability_values=[*modalities, *aliases],
            default=(MODEL_ROLE_GENERATOR,),
        )
        models.append(
            _catalog_model(
                provider_slug="xai",
                provider_name="xAI",
                remote_id=remote_id,
                name=_clean_text(item.get("display_name")) or _clean_text(item.get("name")) or remote_id,
                source_url=XAI_MODELS_API_URL,
                documentation_url=XAI_MODELS_DOC_URL,
                model_roles=roles,
                capabilities=_capabilities_from_values(
                    roles=roles,
                    capability_values=[*modalities, *aliases],
                    text_values=(remote_id, item.get("object"), item.get("owned_by")),
                ),
                context_window_tokens=_first_int(
                    item,
                    "context_window_tokens",
                    "context_window",
                    "context_length",
                    "context_size",
                    "max_context_length",
                    "max_input_tokens",
                ),
                max_output_tokens=_first_int(item, "max_output_tokens", "max_tokens", "output_token_limit"),
                price_input_per_mtok=_xai_input_price_per_mtok(item),
                price_output_per_mtok=_xai_output_price_per_mtok(item),
                raw=item,
                catalog_status=_catalog_status(item),
            )
        )
    return _dedupe_models(models)


OPENAI_MODELS_API_URL = "https://api.openai.com/v1/models"
OPENAI_MODELS_DOC_URL = "https://developers.openai.com/api/reference/resources/models/methods/list"
ANTHROPIC_MODELS_API_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_MODELS_DOC_URL = "https://platform.claude.com/docs/en/api/models/list"
GOOGLE_GEMINI_MODELS_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GOOGLE_GEMINI_MODELS_DOC_URL = "https://ai.google.dev/api/models"
MISTRAL_MODELS_API_URL = "https://api.mistral.ai/v1/models"
MISTRAL_MODELS_DOC_URL = "https://docs.mistral.ai/api/endpoint/models"
COHERE_MODELS_API_URL = "https://api.cohere.com/v1/models"
COHERE_MODELS_DOC_URL = "https://docs.cohere.com/reference/list-models"
XAI_MODELS_API_URL = "https://api.x.ai/v1/models"
XAI_MODELS_DOC_URL = "https://docs.x.ai/developers/rest-api-reference/inference/models"


def _next_page_token(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    return _clean_text(payload.get("next_page_token")) or None


def _google_next_page_token(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    return _clean_text(payload.get("nextPageToken")) or None


def _anthropic_next_page_token(payload: Any) -> str | None:
    if not isinstance(payload, Mapping) or not _truthy(payload.get("has_more")):
        return None
    return _clean_text(payload.get("last_id")) or None


PROVIDER_CATALOG_ADAPTERS: tuple[ProviderCatalogAdapter, ...] = (
    ProviderCatalogAdapter(
        id="openai",
        family="openai",
        provider="OpenAI",
        base_url="https://api.openai.com",
        list_path="/v1/models",
        documentation_url=OPENAI_MODELS_DOC_URL,
        source_url=OPENAI_MODELS_API_URL,
        env_var_groups=(("OPENAI_API_KEY",),),
        auth_scheme="bearer",
        parser=parse_openai_models,
    ),
    ProviderCatalogAdapter(
        id="anthropic",
        family="anthropic",
        provider="Anthropic",
        base_url="https://api.anthropic.com",
        list_path="/v1/models",
        documentation_url=ANTHROPIC_MODELS_DOC_URL,
        source_url=ANTHROPIC_MODELS_API_URL,
        env_var_groups=(("ANTHROPIC_API_KEY",),),
        auth_scheme="anthropic_api_key",
        parser=parse_anthropic_models,
        page_size_param="limit",
        page_token_param="after_id",
        default_page_size=100,
        next_page_token=_anthropic_next_page_token,
    ),
    ProviderCatalogAdapter(
        id="google-gemini",
        family="google-gemini",
        provider="Google",
        base_url="https://generativelanguage.googleapis.com",
        list_path="/v1beta/models",
        documentation_url=GOOGLE_GEMINI_MODELS_DOC_URL,
        source_url=GOOGLE_GEMINI_MODELS_API_URL,
        env_var_groups=(("GEMINI_API_KEY", "GOOGLE_API_KEY"),),
        auth_scheme="google_api_key",
        parser=parse_google_gemini_models,
        page_size_param="pageSize",
        page_token_param="pageToken",
        default_page_size=1000,
        next_page_token=_google_next_page_token,
    ),
    ProviderCatalogAdapter(
        id="mistral",
        family="mistral",
        provider="Mistral",
        base_url="https://api.mistral.ai",
        list_path="/v1/models",
        documentation_url=MISTRAL_MODELS_DOC_URL,
        source_url=MISTRAL_MODELS_API_URL,
        env_var_groups=(("MISTRAL_API_KEY",),),
        auth_scheme="bearer",
        parser=parse_mistral_models,
    ),
    ProviderCatalogAdapter(
        id="cohere",
        family="cohere",
        provider="Cohere",
        base_url="https://api.cohere.com",
        list_path="/v1/models",
        documentation_url=COHERE_MODELS_DOC_URL,
        source_url=COHERE_MODELS_API_URL,
        env_var_groups=(("COHERE_API_KEY",),),
        auth_scheme="bearer",
        parser=parse_cohere_models,
        page_size_param="page_size",
        page_token_param="page_token",
        default_page_size=1000,
        next_page_token=_next_page_token,
    ),
    ProviderCatalogAdapter(
        id="xai",
        family="xai",
        provider="xAI",
        base_url="https://api.x.ai",
        list_path="/v1/models",
        documentation_url=XAI_MODELS_DOC_URL,
        source_url=XAI_MODELS_API_URL,
        env_var_groups=(("XAI_API_KEY",),),
        auth_scheme="bearer",
        parser=parse_xai_models,
    ),
)


def _coerce_adapter(catalog: ProviderCatalogAdapter | Mapping[str, Any] | str) -> ProviderCatalogAdapter:
    if isinstance(catalog, ProviderCatalogAdapter):
        return catalog
    if isinstance(catalog, str):
        return get_provider_catalog_adapter(catalog)
    catalog_id = (
        _clean_text(catalog.get("id"))
        or _clean_text(catalog.get("family"))
        or _clean_text(catalog.get("provider"))
    )
    if catalog_id:
        return get_provider_catalog_adapter(catalog_id)
    raise KeyError("Provider catalog mapping must include id, family, or provider.")


def _require_credentials(adapter: ProviderCatalogAdapter, env: Mapping[str, str]) -> None:
    missing = missing_provider_catalog_env_vars(adapter, env=env)
    if missing:
        choices = [" or ".join(group) for group in missing]
        raise ProviderCatalogNotConfigured(
            f"{adapter.provider} provider catalog requires environment variable: {', '.join(choices)}"
        )


def _credential_value(adapter: ProviderCatalogAdapter, env: Mapping[str, str]) -> str:
    for group in adapter.env_var_groups:
        for name in group:
            value = str(env.get(name) or "").strip()
            if value:
                return value
    raise ProviderCatalogNotConfigured(f"{adapter.provider} provider catalog is not configured.")


def _auth_headers(adapter: ProviderCatalogAdapter, env: Mapping[str, str]) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    if adapter.auth_scheme == "bearer":
        headers["Authorization"] = f"Bearer {_credential_value(adapter, env)}"
    elif adapter.auth_scheme == "anthropic_api_key":
        headers["x-api-key"] = _credential_value(adapter, env)
        headers["anthropic-version"] = "2023-06-01"
    elif adapter.auth_scheme == "google_api_key":
        pass
    else:
        raise ValueError(f"Unsupported provider catalog auth scheme: {adapter.auth_scheme}")
    return headers


def _payload_items(payload: Any, *keys: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        values = payload
    elif isinstance(payload, Mapping):
        values = None
        for key in keys or ("data", "models"):
            candidate = payload.get(key)
            if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
                values = candidate
                break
        if values is None:
            return []
    else:
        return []
    return [item for item in values if isinstance(item, Mapping)]


def _catalog_model(
    *,
    provider_slug: str,
    provider_name: str,
    remote_id: str,
    name: str,
    source_url: str,
    documentation_url: str,
    model_roles: Sequence[str],
    capabilities: Sequence[str],
    raw: Mapping[str, Any],
    context_window_tokens: int | None = None,
    max_output_tokens: int | None = None,
    price_input_per_mtok: float | None = None,
    price_output_per_mtok: float | None = None,
    catalog_status: str | None = None,
    model_type: str | None = None,
    description: str | None = None,
    repo_url: str | None = None,
) -> CatalogModel:
    model: CatalogModel = {
        "id": remote_id,
        "name": name,
        "catalog_model_id": _catalog_model_id(provider_slug, remote_id),
        "provider": provider_name,
        "model_roles": _normalize_roles(model_roles),
        "capabilities": _dedupe_strings(capabilities),
        "metadata_source_name": PROVIDER_API_MODEL_DISCOVERY_SOURCE_NAME,
        "metadata_source_url": source_url,
        "documentation_url": documentation_url,
        "source_url": source_url,
        "catalog_status": catalog_status or _catalog_status(raw),
        "model_type": model_type or "proprietary",
    }
    if context_window_tokens is not None:
        model["context_window_tokens"] = context_window_tokens
    if max_output_tokens is not None:
        model["max_output_tokens"] = max_output_tokens
    if price_input_per_mtok is not None:
        model["price_input_per_mtok"] = price_input_per_mtok
    if price_output_per_mtok is not None:
        model["price_output_per_mtok"] = price_output_per_mtok
    if description:
        model["description"] = description
        model["intended_use_short"] = description
    if repo_url:
        model["repo_url"] = repo_url

    release_values = _release_date_values(raw)
    if release_values:
        model.update(release_values)
    return model


def _catalog_model_id(provider_slug: str, remote_id: str) -> str:
    cleaned = _clean_text(remote_id)
    if "/" in cleaned:
        return cleaned
    return f"{provider_slug}/{cleaned}"


def _dedupe_models(models: Sequence[CatalogModel]) -> list[CatalogModel]:
    seen: set[str] = set()
    deduped: list[CatalogModel] = []
    for model in models:
        key = _clean_text(model.get("catalog_model_id")) or _clean_text(model.get("id"))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(dict(model))
    return deduped


def _google_model_id(item: Mapping[str, Any]) -> str | None:
    for key in ("name", "baseModelId", "id"):
        value = _clean_text(item.get(key))
        if not value:
            continue
        if value.startswith("models/"):
            return value.split("/", 1)[1]
        return value
    return None


def _infer_roles(
    *text_values: Any,
    method_values: Sequence[Any] = (),
    capability_values: Sequence[Any] = (),
    default: Sequence[str] = (MODEL_ROLE_GENERATOR,),
) -> list[str]:
    texts = [_clean_text(value).lower() for value in [*text_values, *method_values, *capability_values]]
    method_capability_texts = [_clean_text(value).lower() for value in [*method_values, *capability_values]]
    joined = " ".join(texts)
    roles: set[str] = set()

    if any(_contains_marker(text, ("embed", "embedding", "embedcontent")) for text in texts):
        if "image" in joined and ("text" in joined or "multimodal" in joined):
            roles.add(MODEL_ROLE_MULTIMODAL_EMBEDDING)
        else:
            roles.add(MODEL_ROLE_EMBEDDING)
    if any(_contains_marker(text, ("rerank", "reranker", "ranking")) for text in texts):
        roles.add(MODEL_ROLE_RERANKER)
    if any(
        _contains_marker(text, ("tts", "text-to-speech", "speech-synthesis", "speech generation"))
        for text in texts
    ):
        roles.add(MODEL_ROLE_TEXT_TO_SPEECH)
    if any(
        _contains_marker(text, ("stt", "speech-to-text", "transcription", "transcribe", "whisper", "asr"))
        for text in texts
    ):
        roles.add(MODEL_ROLE_SPEECH_TO_TEXT)

    generator_markers = (
        "chat",
        "generate",
        "generatecontent",
        "text-generation",
        "completion",
        "completion-chat",
        "completion_chat",
        "language",
    )
    if roles and any(_contains_marker(text, generator_markers) for text in method_capability_texts):
        if not roles or roles == {MODEL_ROLE_GENERATOR}:
            roles.add(MODEL_ROLE_GENERATOR)
        elif MODEL_ROLE_TEXT_TO_SPEECH not in roles and MODEL_ROLE_SPEECH_TO_TEXT not in roles:
            roles.add(MODEL_ROLE_GENERATOR)

    return _normalize_roles(roles or default)


def _normalize_roles(values: Sequence[str] | set[str]) -> list[str]:
    roles = [role for role in values if role in VALID_MODEL_ROLES]
    if not roles:
        roles = [MODEL_ROLE_GENERATOR]
    return sorted(dict.fromkeys(roles), key=lambda role: ROLE_ORDER[role])


def _contains_marker(text: str, markers: Sequence[str]) -> bool:
    normalized = _capability_label(text)
    for marker in markers:
        normalized_marker = _capability_label(marker)
        if normalized_marker and normalized_marker in normalized:
            return True
    return False


def _capabilities_from_values(
    *,
    roles: Sequence[str],
    capability_values: Sequence[Any] = (),
    text_values: Sequence[Any] = (),
) -> list[str]:
    capabilities: list[str] = []
    for role in roles:
        if role == MODEL_ROLE_GENERATOR:
            capabilities.append("text->text")
        elif role == MODEL_ROLE_EMBEDDING:
            capabilities.append("embedding")
        elif role == MODEL_ROLE_MULTIMODAL_EMBEDDING:
            capabilities.append("multimodal-embedding")
        elif role == MODEL_ROLE_RERANKER:
            capabilities.append("reranking")
        elif role == MODEL_ROLE_SPEECH_TO_TEXT:
            capabilities.append("speech-to-text")
        elif role == MODEL_ROLE_TEXT_TO_SPEECH:
            capabilities.append("text-to-speech")

    for value in capability_values:
        if isinstance(value, bool):
            if value:
                capabilities.append("supported")
            continue
        text = _clean_text(value)
        if text and text.lower() not in {"false", "none", "null"}:
            capabilities.append(text)
        label = _capability_label(value)
        if label and label not in {"false", "none", "null"}:
            capabilities.append(label)

    for value in text_values:
        if isinstance(value, bool):
            if value:
                capabilities.append("supported")
            continue
        label = _capability_label(value)
        if label and label not in {"false", "none", "null"}:
            capabilities.append(label)

    joined = " ".join(_clean_text(value).lower() for value in text_values)
    if "vision" in joined or "image" in joined:
        capabilities.append("vision")
    if "tool" in joined or "function" in joined:
        capabilities.append("function-calling")
    if "moderation" in joined:
        capabilities.append("moderation")

    return _dedupe_strings(capabilities)


def _capability_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        values: list[str] = []
        for key, item_value in value.items():
            if isinstance(item_value, bool):
                if item_value:
                    values.append(str(key))
            elif item_value not in (None, "", [], {}):
                values.append(f"{key}:{item_value}")
        return values
    return _string_list(value)


def _capability_label(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = _CAMEL_BOUNDARY_RE.sub("-", text)
    text = text.replace("_", "-").replace("/", "-").lower()
    text = _NON_WORD_RE.sub("-", text).strip("-")
    if text == "text-text":
        return "text->text"
    return text


def _dedupe_strings(values: Sequence[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _catalog_status(item: Mapping[str, Any]) -> str:
    if _truthy(item.get("is_deprecated")) or _truthy(item.get("deprecated")) or _truthy(item.get("archived")):
        return "deprecated"
    # Authenticated provider listings prove availability to one account, not
    # general production suitability. Curated tracked rows remain tracked when
    # this provisional evidence resolves to an existing model.
    return "provisional"


def _release_date_values(item: Mapping[str, Any]) -> dict[str, str] | None:
    for key in (
        "release_date",
        "releaseDate",
        "released",
        "released_at",
        "releasedAt",
        "launch_date",
        "launchDate",
    ):
        value = item.get(key)
        release_date = _date_from_value(value)
        if release_date:
            return {
                "release_date": release_date,
                "release_date_precision": _release_date_precision(release_date),
                "release_date_confidence": "high",
            }
    return None


def _date_from_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 0:
        if value > 10_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    text = _clean_text(value)
    if not text:
        return None
    if "T" in text:
        parsed = _parse_datetime(text)
        if parsed:
            return parsed.date().isoformat()
    if _DATE_RE.match(text):
        return text
    return None


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _release_date_precision(value: str) -> str:
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return "day"
    if re.match(r"^\d{4}-Q[1-4]$", value):
        return "quarter"
    if re.match(r"^\d{4}-\d{2}$", value):
        return "month"
    return "year"


def _first_int(item: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _optional_int(item.get(key))
        if value is not None:
            return value
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _clean_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return int(float(match.group(0)))
    except ValueError:
        return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value).replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _xai_input_price_per_mtok(item: Mapping[str, Any]) -> float | None:
    direct = _first_float(
        item,
        "price_input_per_mtok",
        "input_price_per_mtok",
        "input_cost_per_million_tokens",
        "prompt_text_price_per_mtok",
    )
    if direct is not None:
        return direct
    cents_per_100m = _first_float(
        item,
        "prompt_text_token_price",
        "prompt_text_token_price_long_context",
        "input_text_token_price",
    )
    if cents_per_100m is not None:
        return round(cents_per_100m / 10000.0, 6)
    return _nested_pricing_value(item, ("input", "prompt"))


def _xai_output_price_per_mtok(item: Mapping[str, Any]) -> float | None:
    direct = _first_float(
        item,
        "price_output_per_mtok",
        "output_price_per_mtok",
        "output_cost_per_million_tokens",
        "completion_text_price_per_mtok",
    )
    if direct is not None:
        return direct
    cents_per_100m = _first_float(
        item,
        "completion_text_token_price",
        "completion_text_token_price_long_context",
        "output_text_token_price",
    )
    if cents_per_100m is not None:
        return round(cents_per_100m / 10000.0, 6)
    return _nested_pricing_value(item, ("output", "completion"))


def _first_float(item: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(item.get(key))
        if value is not None:
            return value
    return None


def _nested_pricing_value(item: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    pricing = item.get("pricing")
    if not isinstance(pricing, Mapping):
        return None
    for key in keys:
        for candidate in (key, f"{key}_per_mtok", f"{key}_per_million_tokens"):
            value = _optional_float(pricing.get(candidate))
            if value is not None:
                return value
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values: Sequence[Any] = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        return []
    return [_clean_text(item) for item in values if _clean_text(item)]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _clean_text(value).lower()
    return text in {"1", "true", "yes", "y", "deprecated", "archived"}


def _key(value: Any) -> str:
    return _capability_label(value)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "CatalogModel",
    "ProviderCatalogAdapter",
    "ProviderCatalogError",
    "ProviderCatalogNotConfigured",
    "fetch_provider_api_catalog_models",
    "fetch_provider_api_catalog_payloads",
    "get_provider_catalog_adapter",
    "list_provider_catalog_adapters",
    "missing_provider_catalog_env_vars",
    "parse_anthropic_models",
    "parse_cohere_models",
    "parse_google_gemini_models",
    "parse_mistral_models",
    "parse_openai_models",
    "parse_provider_api_catalog_models",
    "parse_xai_models",
    "provider_api_catalogs",
    "provider_catalog_env_requirements",
]
