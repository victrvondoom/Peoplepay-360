"""Backward-compatible shim.

`gemini_service` used to be a Gemini-only singleton; it is now an alias for
the provider-agnostic `llm_service`, which resolves to whichever backend
LLM_PROVIDER selects (gemini or nvidia). Existing `from app.llm.gemini.service
import gemini_service` imports keep working unchanged. New code should import
`llm_service` from `app.llm.service` directly.
"""
from __future__ import annotations

from app.llm.service import llm_service as gemini_service

__all__ = ["gemini_service"]
