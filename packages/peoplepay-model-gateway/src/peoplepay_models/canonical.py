"""Canonical types: conversation, capabilities, registry records, requests, responses.

Conversation state NEVER lives in a provider-specific shape; adapters translate.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now() -> float:
    return time.time()


class Capability(str, Enum):
    TEXT = "text"
    VISION = "vision"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"
    REASONING = "reasoning"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    IMAGE_GENERATION = "image_generation"
    EMBEDDINGS = "embeddings"
    LONG_CONTEXT = "long_context"
    FILES = "files"
    COMPUTER_USE = "computer_use"
    DECISION_BOOLEAN = "decision_boolean"
    DECISION_CHOICE = "decision_choice"
    DECISION_SCORE = "decision_score"
    LOCAL_EXECUTION = "local_execution"


class Evidence(str, Enum):
    """Why we believe a capability exists. Never claim without one of these."""
    PROVIDER_METADATA = "provider_metadata"
    CAPABILITY_TEST = "capability_test"
    USER_OVERRIDE = "user_override"   # advanced; may be wrong
    STATIC_FALLBACK = "static_fallback"


class ProviderType(str, Enum):
    DIRECT = "DIRECT"
    AGGREGATOR = "AGGREGATOR"
    ENTERPRISE_PLATFORM = "ENTERPRISE_PLATFORM"
    LOCAL = "LOCAL"
    CUSTOM = "CUSTOM"
    DECISION = "DECISION"


class Health(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class Privacy(str, Enum):
    """Where a route sends data. Ordered from most to least contained."""
    LOCAL = "local"            # never leaves the configured local boundary
    ORGANIZATION = "organization"  # org-approved enterprise route / org gateway
    CLOUD = "cloud"            # third-party cloud

    @property
    def rank(self) -> int:
        return {"local": 0, "organization": 1, "cloud": 2}[self.value]


class DataClass(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"


class Reasoning(str, Enum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    DEEP = "DEEP"
    AUTO = "AUTO"


class FallbackMode(str, Enum):
    ASK = "ASK"
    AUTOMATIC = "AUTOMATIC"
    NONE = "NONE"


class RoutingPolicy(str, Enum):
    BEST_QUALITY = "BEST_QUALITY"
    BALANCED = "BALANCED"
    FASTEST = "FASTEST"
    LOW_COST = "LOW_COST"
    PRIVACY_FIRST = "PRIVACY_FIRST"
    LOCAL_ONLY = "LOCAL_ONLY"
    CUSTOM = "CUSTOM"


# ---------------------------------------------------------------- conversation

@dataclass
class TextPart:
    text: str
    kind: str = "text"


@dataclass
class ImagePart:
    """Inline bytes (base64) or a URL. ``media_type`` e.g. image/png."""
    media_type: str = "image/png"
    data_b64: str | None = None
    url: str | None = None
    kind: str = "image"


@dataclass
class FilePart:
    name: str
    media_type: str = "application/octet-stream"
    data_b64: str | None = None
    url: str | None = None
    kind: str = "file"


@dataclass
class ToolCallPart:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    kind: str = "tool_call"


@dataclass
class ToolResultPart:
    call_id: str
    content: str
    is_error: bool = False
    kind: str = "tool_result"


@dataclass
class StructuredPart:
    data: Any
    schema_name: str | None = None
    kind: str = "structured"


Part = TextPart | ImagePart | FilePart | ToolCallPart | ToolResultPart | StructuredPart

_PART_TYPES = {"text": TextPart, "image": ImagePart, "file": FilePart, "tool_call": ToolCallPart,
               "tool_result": ToolResultPart, "structured": StructuredPart}


def part_from_dict(d: dict) -> Part:
    cls = _PART_TYPES.get(d.get("kind", "text"))
    if cls is None:
        raise ValueError(f"unknown part kind {d.get('kind')!r}")
    fields = {k: v for k, v in d.items() if k != "kind"}
    return cls(**fields)


@dataclass
class ServedBy:
    """Which route actually produced an assistant message. Survives model removal."""
    provider_id: str
    connection_id: str
    model_id: str            # canonical id at the time
    provider_model_id: str
    route: str
    requested: str | None = None
    fallback_reason: str | None = None


@dataclass
class Message:
    role: str                 # system | user | assistant | tool
    parts: list[Part]
    id: str = field(default_factory=lambda: new_id("msg"))
    created_at: float = field(default_factory=now)
    served_by: ServedBy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, TextPart))

    def part_kinds(self) -> set[str]:
        return {p.kind for p in self.parts}

    def to_dict(self) -> dict:
        return {"id": self.id, "role": self.role, "created_at": self.created_at,
                "parts": [asdict(p) for p in self.parts], "metadata": self.metadata,
                "served_by": asdict(self.served_by) if self.served_by else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        sb = d.get("served_by")
        return cls(role=d["role"], parts=[part_from_dict(p) for p in d.get("parts", [])],
                   id=d.get("id") or new_id("msg"), created_at=d.get("created_at", now()),
                   served_by=ServedBy(**sb) if sb else None, metadata=d.get("metadata") or {})

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls("user", [TextPart(text)])

    @classmethod
    def assistant(cls, text: str) -> "Message":
        return cls("assistant", [TextPart(text)])


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: new_id("conv"))
    owner: str = ""
    title: str = ""
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=now)

    def add(self, message: Message) -> Message:
        self.messages.append(message)
        return message

    def required_input_kinds(self) -> set[str]:
        kinds: set[str] = set()
        for m in self.messages:
            kinds |= m.part_kinds()
        return kinds

    def to_dict(self) -> dict:
        return {"id": self.id, "owner": self.owner, "title": self.title,
                "created_at": self.created_at, "messages": [m.to_dict() for m in self.messages]}

    @classmethod
    def from_dict(cls, d: dict) -> "Conversation":
        return cls(id=d["id"], owner=d.get("owner", ""), title=d.get("title", ""),
                   created_at=d.get("created_at", now()),
                   messages=[Message.from_dict(m) for m in d.get("messages", [])])


@dataclass
class ToolDefinition:
    """Canonical tool. Execution authority stays with PeoplePay, never the model."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})


# ---------------------------------------------------------------- registry

@dataclass
class CapabilitySet:
    """Capabilities with the evidence for each. Unknown is *absent*, not False."""
    items: dict[str, str] = field(default_factory=dict)   # capability -> Evidence value

    def has(self, cap: Capability) -> bool:
        return cap.value in self.items

    def add(self, cap: Capability, evidence: Evidence) -> None:
        self.items[cap.value] = evidence.value

    def names(self) -> list[str]:
        return sorted(self.items)

    @classmethod
    def of(cls, evidence: Evidence, *caps: Capability) -> "CapabilitySet":
        cs = cls()
        for c in caps:
            cs.add(c, evidence)
        return cs


@dataclass
class ModelDefinition:
    """Model identity, independent of how it is reached (see ProviderModelRoute)."""
    canonical_model_id: str     # e.g. "family/name" -- normalized, vendor-neutral where derivable
    display_name: str
    model_family: str | None = None
    context_window: int | None = None
    max_output: int | None = None
    kind: str = "chat"          # chat | decision | embedding | other


@dataclass
class ProviderModelRoute:
    """One way to reach a ModelDefinition: a model on a provider connection."""
    canonical_model_id: str
    provider_model_id: str
    provider_id: str
    connection_id: str
    route: str                  # human label: "Direct", "Bedrock", "OpenRouter", "Local (Ollama)" ...
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    privacy: Privacy = Privacy.CLOUD
    local: bool = False
    region: str | None = None
    availability: str = "available"       # available | unavailable | deprecated | unknown
    status: str = "ok"
    pricing: dict[str, float] | None = None   # per-1M-token, ONLY if reliably known
    last_discovered_at: float | None = None
    display_name: str = ""
    model_family: str | None = None
    context_window: int | None = None
    max_output: int | None = None
    kind: str = "chat"
    source: str = "discovery"             # discovery | static | manual | override

    @property
    def key(self) -> str:
        return f"{self.connection_id}::{self.provider_model_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderModelRoute":
        d = dict(d)
        d["capabilities"] = CapabilitySet(items=dict((d.get("capabilities") or {}).get("items", {})))
        d["privacy"] = Privacy(d.get("privacy", "cloud"))
        return cls(**d)


@dataclass
class ProviderConnection:
    id: str
    provider_type: str          # manifest id: openai, anthropic, ollama, ...
    display_name: str
    owner_scope: str            # "user:<id>" | "org:<id>" | "system"
    configuration: dict[str, Any] = field(default_factory=dict)   # non-secret
    credential_ref: str | None = None
    enabled: bool = True
    created_at: float = field(default_factory=now)
    last_validated_at: float | None = None
    validation_status: str = "not_validated"   # not_validated | ok | invalid
    alias: str | None = None
    system: bool = False        # registered from environment; not user-removable

    def public(self) -> dict:
        d = asdict(self)
        d["has_credential"] = bool(self.credential_ref)
        d.pop("credential_ref", None)
        return d


# ---------------------------------------------------------------- invocation

@dataclass
class ModelSelection:
    """What the user (or caller) asked for."""
    mode: str = "auto"      # auto | fast | balanced | deep | local | model
    model: str | None = None            # canonical model id or route key or alias
    connection_id: str | None = None    # pin a provider route
    one_shot: bool = False


@dataclass
class InferenceRequest:
    conversation: Conversation | None = None
    messages: list[Message] = field(default_factory=list)   # used when no conversation
    system: str | None = None
    selection: ModelSelection = field(default_factory=ModelSelection)
    tools: list[ToolDefinition] = field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning: Reasoning = Reasoning.AUTO
    stream: bool = False
    data_class: DataClass = DataClass.INTERNAL
    routing_policy: RoutingPolicy | None = None
    fallback_mode: FallbackMode | None = None
    task: str = "chat"
    metadata: dict[str, Any] = field(default_factory=dict)
    provider_options: dict[str, Any] = field(default_factory=dict)

    def history(self) -> list[Message]:
        return list(self.conversation.messages) if self.conversation else list(self.messages)


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    estimated_cost: float | None = None   # None = unknown; never 0 by guess


@dataclass
class Attempt:
    route_key: str
    provider_id: str
    model_id: str
    status: str                # ok | error | skipped
    error_code: str | None = None
    latency_ms: float | None = None
    reason: str | None = None


@dataclass
class InferenceResponse:
    parts: list[Part]
    model_requested: str | None
    served_by: ServedBy
    usage: Usage = field(default_factory=Usage)
    latency_ms: float | None = None
    finish_reason: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    routing_explanation: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    invocation_id: str = field(default_factory=lambda: new_id("inv"))

    @property
    def text(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, TextPart))

    def to_message(self) -> Message:
        return Message("assistant", list(self.parts), served_by=self.served_by,
                       metadata={"invocation_id": self.invocation_id, "notes": self.notes})

    def to_dict(self) -> dict:
        return {"text": self.text, "parts": [asdict(p) for p in self.parts],
                "model_requested": self.model_requested, "served_by": asdict(self.served_by),
                "usage": asdict(self.usage), "latency_ms": self.latency_ms,
                "finish_reason": self.finish_reason, "attempts": [asdict(a) for a in self.attempts],
                "routing_explanation": self.routing_explanation, "notes": self.notes,
                "invocation_id": self.invocation_id}


@dataclass
class StreamEvent:
    """Canonical stream event. Provider framing never leaves the adapter."""
    type: str   # response.started|text.delta|tool.started|tool.completed|usage|response.completed|error
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, **self.data}


# ---------------------------------------------------------------- decisions

@dataclass
class DecisionQuestion:
    id: str
    kind: str                    # BOOLEAN | CHOICE | SCORE | RATING
    prompt: str
    choices: list[str] = field(default_factory=list)
    scale: tuple[float, float] | None = None


@dataclass
class DecisionAnswer:
    question_id: str
    kind: str
    value: Any                   # bool | str | float
    confidence: float | None = None   # None = provider did not report; never invented
