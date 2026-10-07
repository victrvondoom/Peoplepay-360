"""Extension-facing client: ask for a CAPABILITY, not a vendor or an API key.

    models = ModelsClient(gateway, owner)
    models.generate("reasoning.deep", "Compare these suppliers", ...)

The gateway resolves the route (privacy, health, fallback). Extensions that keep their
own AI configuration keep working; this is opt-in and additive (SDK v1 is untouched).
"""
from __future__ import annotations

from typing import Any

from .canonical import (DataClass, DecisionQuestion, ImagePart, InferenceRequest, Message, ModelSelection,
                        Reasoning, TextPart, ToolDefinition)
from .errors import ErrorCode, GatewayError
from .gateway import ModelGateway

# capability name -> (selection mode, requires vision, reasoning)
CAPABILITIES = {
    "text.generate": ("auto", False, Reasoning.AUTO),
    "text.fast": ("fast", False, Reasoning.FAST),
    "reasoning.deep": ("deep", False, Reasoning.DEEP),
    "vision.analyze": ("auto", True, Reasoning.AUTO),
    "code.generate": ("auto", False, Reasoning.STANDARD),
}


class ModelsClient:
    def __init__(self, gateway: ModelGateway, owner: str, *, source: str = "extension"):
        self.gw, self.owner, self.source = gateway, owner, source

    def generate(self, capability: str, prompt: str, *, images: list[ImagePart] | None = None, system: str | None = None,
                 exact_model: str | None = None, data_class: DataClass = DataClass.INTERNAL, tools: list[ToolDefinition] | None = None,
                 response_schema: dict | None = None, **kw: Any):
        if capability.startswith("decision."):
            raise GatewayError(ErrorCode.INVALID_REQUEST, "use classify() for decision.* capabilities")
        if capability not in CAPABILITIES:
            raise GatewayError(ErrorCode.UNSUPPORTED_CAPABILITY, f"unknown capability {capability!r}")
        mode, vision, reasoning = CAPABILITIES[capability]
        if vision and not images:
            raise GatewayError(ErrorCode.INVALID_REQUEST, "vision.analyze needs at least one image")
        sel = ModelSelection("model", exact_model) if exact_model else ModelSelection(mode)
        req = InferenceRequest(messages=[Message("user", [TextPart(prompt), *(images or [])])], system=system, selection=sel,
                               reasoning=reasoning, data_class=data_class, tools=tools or [], response_schema=response_schema,
                               task=kw.pop("task", "background"), metadata={"source": self.source}, **kw)
        resp = self.gw.infer(self.owner, req)
        return resp

    def classify(self, state: dict, questions: list[DecisionQuestion]) -> dict:
        return self.gw.decide(self.owner, state, questions)
