import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


def _load_dotenv() -> None:
    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in os.environ or os.environ.get(key, "").strip() == "":
            os.environ[key] = value


_load_dotenv()


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value


def _env(name: str, default: str) -> str:
    return os.getenv(name) or default


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = "PROXY API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    vector_store_backend: str = "jsonl"
    graph_store_backend: str = "jsonl"
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    database_url: str | None = None
    storage_bucket_documents: str = "case-documents"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection_prefix: str = "proxy"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 60
    max_upload_mb: int = 25
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_reasoning_model: str = "gemini-2.5-flash"
    gemini_router_model: str = "gemini-2.5-flash-lite"
    gemini_planner_model: str = "gemini-2.5-flash-lite"
    gemini_response_model: str = "gemini-2.5-flash"
    gemini_summarization_model: str = "gemini-2.5-flash-lite"
    gemini_ocr_model: str = "gemini-2.5-flash"
    # This gates the ONLY step that turns raw, concatenated per-specialist
    # template text into one synthesized, deduplicated, causally-reasoned
    # answer (see run_response_agent/_synthesize_final_answer) -- with this
    # off, the user-facing "final_answer" for every multi-specialist domain
    # is literally 2-3 specialists' near-identical template output pasted
    # back to back, addressed in third person, with zero deduplication or
    # sequencing. Defaulting to False (and never being set in the deployed
    # environment) meant this had silently never run in production.
    response_agent_llm_enabled: bool = True
    disable_external_llm: bool = False
    embedding_model: str = "gemini-embedding-001"

    llm_provider: str = "gemini"
    llm_model: str | None = None
    llm_fallback_model: str = "meta/llama-3.1-8b-instruct"
    llm_max_retries: int = 2
    llm_completion_timeout_seconds: int = 25
    llm_embedding_timeout_seconds: int = 15
    llm_http_timeout_seconds: int = 20
    llm_circuit_breaker_threshold: int = 3
    llm_circuit_breaker_cooldown_seconds: int = 60
    gemini_embedding_dimension: int = 768
    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_reasoning_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_router_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_planner_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_response_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_summarization_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_ocr_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_vision_model: str = "meta/llama-3.2-11b-vision-instruct"
    nvidia_kg_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    nvidia_embedding_dimension: int = 1024
    nvidia_request_timeout_seconds: int = 25
    nvidia_embedding_timeout_seconds: int = 15
    nvidia_max_retries: int = 2
    nvidia_rate_limit_per_minute: int = 40
    # Chat completions previously had no max_tokens at all, so they fell
    # back to the API's own default cap -- fine for a single short answer,
    # but agents that generate several full documents in one JSON response
    # (e.g. the Negotiation Agent's 4 letters) would get silently truncated
    # mid-object, producing invalid JSON that fell back to empty fields.
    nvidia_max_tokens: int = 3072
    cache_enabled: bool = True
    cache_embedding_ttl_seconds: int = 604800
    cache_prompt_ttl_seconds: int = 3600
    cache_graph_ttl_seconds: int = 600
    cache_chunks_ttl_seconds: int = 300
    health_probe_cache_ttl_seconds: int = 10
    jwt_audience: str = "authenticated"
    jwt_issuer: str | None = None
    supabase_jwt_secret: str | None = None
    admin_api_key: str | None = None
    tavily_api_key: str | None = None
    web_search_cache_ttl_seconds: int = 86400
    web_search_rate_limit_per_minute: int = 10
    ocr_max_pages: int = 25
    ocr_page_concurrency: int = 3
    ocr_max_image_side: int = 1600
    ocr_max_tokens: int = 4096
    ocr_request_timeout_seconds: int = 90


@lru_cache
def get_settings() -> Settings:
    gemini_model = _env("GEMINI_MODEL", "gemini-2.5-flash")
    return Settings(
        environment=_env("ENVIRONMENT", "development"),
        cors_origins=_csv_env("CORS_ORIGINS", ["http://localhost:3000", "http://localhost:3001"]),
        vector_store_backend=_env("VECTOR_STORE_BACKEND", "jsonl"),
        graph_store_backend=_env("GRAPH_STORE_BACKEND", "jsonl"),
        supabase_url=_optional_env("SUPABASE_URL"),
        supabase_anon_key=_optional_env("SUPABASE_ANON_KEY"),
        supabase_service_role_key=_optional_env("SUPABASE_SERVICE_ROLE_KEY"),
        database_url=_optional_env("DATABASE_URL"),
        storage_bucket_documents=_env("STORAGE_BUCKET_DOCUMENTS", "case-documents"),
        qdrant_url=_env("QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=_optional_env("QDRANT_API_KEY"),
        qdrant_collection_prefix=_env("QDRANT_COLLECTION_PREFIX", "proxy"),
        neo4j_uri=_env("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=_env("NEO4J_USER", "neo4j"),
        neo4j_password=_optional_env("NEO4J_PASSWORD"),
        redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
        rate_limit_per_minute=int(_env("RATE_LIMIT_PER_MINUTE", "60")),
        max_upload_mb=int(_env("MAX_UPLOAD_MB", "25")),
        gemini_api_key=_optional_env("GEMINI_API_KEY"),
        gemini_model=gemini_model,
        gemini_reasoning_model=_env("GEMINI_REASONING_MODEL", gemini_model),
        gemini_router_model=_env("GEMINI_ROUTER_MODEL", "gemini-2.5-flash-lite"),
        gemini_planner_model=_env("GEMINI_PLANNER_MODEL", "gemini-2.5-flash-lite"),
        gemini_response_model=_env("GEMINI_RESPONSE_MODEL", gemini_model),
        gemini_summarization_model=_env("GEMINI_SUMMARIZATION_MODEL", "gemini-2.5-flash-lite"),
        gemini_ocr_model=_env("GEMINI_OCR_MODEL", gemini_model),
        response_agent_llm_enabled=_bool_env("RESPONSE_AGENT_LLM_ENABLED", True),
        disable_external_llm=_bool_env("DISABLE_EXTERNAL_LLM", False),
        embedding_model=_env(
            "EMBEDDING_MODEL",
            "nvidia/nv-embedqa-e5-v5" if _env("LLM_PROVIDER", "gemini") == "nvidia" else "gemini-embedding-001",
        ),
        llm_provider=_env("LLM_PROVIDER", "gemini"),
        llm_model=_optional_env("LLM_MODEL"),
        llm_fallback_model=_env("LLM_FALLBACK_MODEL", "meta/llama-3.1-8b-instruct"),
        llm_max_retries=int(_env("MAX_RETRIES", "2")),
        llm_completion_timeout_seconds=int(_env("TIMEOUT", "25")),
        llm_embedding_timeout_seconds=int(_env("EMBEDDING_TIMEOUT", "15")),
        llm_http_timeout_seconds=int(_env("HTTP_TIMEOUT", "20")),
        llm_circuit_breaker_threshold=int(_env("CIRCUIT_BREAKER_THRESHOLD", "3")),
        llm_circuit_breaker_cooldown_seconds=int(_env("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")),
        gemini_embedding_dimension=int(_env("GEMINI_EMBEDDING_DIMENSION", "768")),
        nvidia_api_key=_optional_env("NVIDIA_API_KEY"),
        nvidia_base_url=_env("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        nvidia_reasoning_model=_env("NVIDIA_REASONING_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_router_model=_env("NVIDIA_ROUTER_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_planner_model=_env("NVIDIA_PLANNER_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_response_model=_env("NVIDIA_RESPONSE_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_summarization_model=_env("NVIDIA_SUMMARIZATION_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_ocr_model=_env("NVIDIA_OCR_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_vision_model=_env(
            "NVIDIA_VISION_MODEL",
            "meta/llama-3.2-11b-vision-instruct",
        ),
        nvidia_kg_model=_env("NVIDIA_KG_MODEL", _optional_env("LLM_MODEL") or "meta/llama-3.1-8b-instruct"),
        nvidia_embedding_model=_env("EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5"),
        nvidia_embedding_dimension=int(_env("NVIDIA_EMBEDDING_DIMENSION", "1024")),
        nvidia_request_timeout_seconds=int(_env("TIMEOUT", "25")),
        nvidia_embedding_timeout_seconds=int(_env("EMBEDDING_TIMEOUT", "15")),
        nvidia_max_retries=int(_env("MAX_RETRIES", "2")),
        nvidia_rate_limit_per_minute=int(_env("NVIDIA_RATE_LIMIT_PER_MINUTE", "40")),
        nvidia_max_tokens=int(_env("NVIDIA_MAX_TOKENS", "3072")),
        cache_enabled=_bool_env("CACHE_ENABLED", True),
        cache_embedding_ttl_seconds=int(_env("CACHE_EMBEDDING_TTL_SECONDS", "604800")),
        cache_prompt_ttl_seconds=int(_env("CACHE_PROMPT_TTL_SECONDS", "3600")),
        cache_graph_ttl_seconds=int(_env("CACHE_GRAPH_TTL_SECONDS", "600")),
        cache_chunks_ttl_seconds=int(_env("CACHE_CHUNKS_TTL_SECONDS", "300")),
        health_probe_cache_ttl_seconds=int(_env("HEALTH_PROBE_CACHE_TTL_SECONDS", "10")),
        jwt_audience=_env("JWT_AUDIENCE", "authenticated"),
        jwt_issuer=_optional_env("JWT_ISSUER"),
        supabase_jwt_secret=_optional_env("SUPABASE_JWT_SECRET"),
        admin_api_key=_optional_env("ADMIN_API_KEY"),
        tavily_api_key=_optional_env("TAVILY_API_KEY"),
        web_search_cache_ttl_seconds=int(_env("WEB_SEARCH_CACHE_TTL_SECONDS", "86400")),
        web_search_rate_limit_per_minute=int(_env("WEB_SEARCH_RATE_LIMIT_PER_MINUTE", "10")),
        ocr_max_pages=int(_env("OCR_MAX_PAGES", "25")),
        ocr_page_concurrency=int(_env("OCR_PAGE_CONCURRENCY", "3")),
        ocr_max_image_side=int(_env("OCR_MAX_IMAGE_SIDE", "1600")),
        ocr_max_tokens=int(_env("OCR_MAX_TOKENS", "4096")),
        ocr_request_timeout_seconds=int(_env("OCR_TIMEOUT", "90")),
    )

