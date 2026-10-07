"""Capability inference rules -- the ONE place model-name patterns live.

Used only where a provider's catalog carries no capability metadata (e.g. an
OpenAI-style ``GET /models`` returns ids only). Results are tagged
``Evidence.STATIC_FALLBACK`` so the UI and router can treat them as weaker than
provider metadata or a capability test, and ``test_capability`` can upgrade them.
Routing code must never match on model names; it reads capabilities.

Patterns are deliberately coarse and kind-first: non-chat models (embeddings,
speech, image generation, moderation) are excluded from chat lists.
"""
from __future__ import annotations

import re

from .canonical import Capability as C

# (regex on lower-cased provider model id, kind)
KIND_RULES: list[tuple[str, str]] = [
    (r"embed|embedding|bge-|e5-|nv-embed", "embedding"),
    (r"rerank", "reranker"),
    (r"whisper|tts|speech|transcribe|audio-preview-nope", "audio"),
    (r"dall-e|gpt-image|image-gen|imagen|stable-diffusion|sdxl|flux", "image_generation"),
    (r"moderation|guard|safety", "other"),
]

# (regex, capabilities) -- additive.
CAPABILITY_RULES: list[tuple[str, tuple[C, ...]]] = [
    (r"claude", (C.VISION, C.TOOLS, C.STRUCTURED_OUTPUT)),
    (r"gpt-4o|gpt-4\.1|gpt-5|gpt-4-turbo|\bo[134]\b|^o[134]-", (C.VISION, C.TOOLS, C.STRUCTURED_OUTPUT)),
    (r"gpt-3\.5", (C.TOOLS,)),
    (r"(^|[/.\-])o[134]($|[\-:])|gpt-5|reason|thinking|deepseek-r1|qwq", (C.REASONING,)),
    (r"vision|-vl|llava|pixtral|gemma-?[34]|llama-?3\.2.*(11|90)b|nova-(lite|pro|premier)|minicpm-v", (C.VISION,)),
    (r"llama-?3\.[1-9]|qwen|mistral|mixtral|nemotron|gpt-oss|command-r|nova|granite", (C.TOOLS,)),
]


def infer_kind(model_id: str) -> str:
    low = model_id.lower()
    for pat, kind in KIND_RULES:
        if re.search(pat, low):
            return kind
    return "chat"


def infer_capabilities(model_id: str) -> set[C]:
    low = model_id.lower()
    caps: set[C] = set()
    for pat, add in CAPABILITY_RULES:
        if re.search(pat, low):
            caps.update(add)
    return caps


# Weak, name-based tier hints. Consulted ONLY when neither a user class assignment nor
# provider metadata decides a model's tier. Single location by design.
TIER_FAST = r"mini|nano|haiku|flash|lite|small|instant|tiny|turbo|(^|[^0-9])([1-9]|1[0-3])b([^a-z]|$)"
TIER_DEEP = r"opus|ultra|large|reason|thinking|(^|[^a-z])o[13]([^0-9]|$)|405b|70b|72b|\bpro\b|-pro"


def tier_hint(model_id: str) -> str | None:
    low = model_id.lower()
    if re.search(TIER_DEEP, low):
        return "deep"
    if re.search(TIER_FAST, low):
        return "fast"
    return None


def canonical_id(model_id: str) -> str:
    """Best-effort vendor-neutral id so the same model on several routes can be grouped.

    Conservative: strips route-specific decoration only (vendor prefix, Bedrock region
    profile + ``-v1:0`` suffix, ``:free`` style tags). Unknown stays distinct -- a wrong
    merge is worse than a missed one.
    """
    s = model_id.lower().strip()
    s = s.split("/", 1)[-1] if "/" in s else s
    s = re.sub(r"^(us|eu|apac|global)\.", "", s)
    s = re.sub(r"^(anthropic|amazon|meta|mistral|cohere|ai21|deepseek|openai)\.", "", s)
    s = re.sub(r"-v\d+(:\d+)?$", "", s)
    s = re.sub(r":(free|extended|beta|nitro|floor|thinking)$", "", s)
    s = s.replace(".", "-") if re.search(r"\d\.\d", s) else s
    return s
