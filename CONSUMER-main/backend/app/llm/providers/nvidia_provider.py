from __future__ import annotations

import base64
import logging
from typing import AsyncIterator

import httpx

from app.core.config import Settings
from app.llm.base import LLMProvider, LLMPurpose
from app.llm.observability import RateLimiter, build_retrying, log_llm_call

logger = logging.getLogger("app.llm.nvidia")


class _TokenLimitExceeded(Exception):
    """The embedding model rejected a text as longer than its max token
    window. Not retryable as-is (retrying the same text won't help) — the
    caller shrinks the text and retries with a smaller version instead."""


class NvidiaProvider(LLMProvider):
    """NVIDIA NIM provider using the OpenAI-compatible /chat/completions and
    /embeddings endpoints at integrate.api.nvidia.com (or a self-hosted NIM)."""

    name = "nvidia"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._rate_limiter = RateLimiter(settings.nvidia_rate_limit_per_minute)

    @property
    def embedding_dimension(self) -> int:
        return self.settings.nvidia_embedding_dimension

    def _configured(self) -> bool:
        return bool(self.settings.nvidia_api_key) and not self.settings.disable_external_llm

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.nvidia_api_key}",
            "Content-Type": "application/json",
        }

    def embedding_mode(self) -> str:
        if self._configured():
            return "nvidia"
        if self.settings.environment == "test" or self.settings.disable_external_llm:
            return "hash_fallback"
        return "nvidia"

    def model_for(self, purpose: LLMPurpose | None = None, model_name: str | None = None) -> str:
        if model_name:
            return model_name
        if purpose == "router":
            return self.settings.nvidia_router_model
        if purpose == "planner":
            return self.settings.nvidia_planner_model
        if purpose == "response":
            return self.settings.nvidia_response_model
        if purpose == "summarization":
            return self.settings.nvidia_summarization_model
        if purpose == "ocr":
            return self.settings.nvidia_ocr_model
        if purpose == "kg_extraction":
            return self.settings.nvidia_kg_model
        return self.settings.nvidia_reasoning_model

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> str:
        selected_model = self.model_for(purpose, model_name)
        async with log_llm_call(self.name, "generate", purpose, selected_model) as record:
            if not self._configured():
                if self.settings.environment == "test" or self.settings.disable_external_llm:
                    return self._offline_response(prompt)
                raise RuntimeError("NVIDIA API is not configured. Please set NVIDIA_API_KEY in your environment/dotenv file.")

            payload = {
                "model": selected_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": self.settings.nvidia_max_tokens,
            }

            async def _call() -> httpx.Response:
                await self._rate_limiter.acquire()
                async with httpx.AsyncClient(timeout=self.settings.nvidia_request_timeout_seconds) as client:
                    resp = await client.post(
                        f"{self.settings.nvidia_base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp

            try:
                retryer = build_retrying(self.settings.nvidia_max_retries)
                async for attempt in retryer:
                    with attempt:
                        record["retries"] = attempt.retry_state.attempt_number - 1
                        response = await _call()
            except Exception as exc:
                if self.settings.environment == "test" or self.settings.disable_external_llm:
                    return self._offline_response(prompt)
                raise RuntimeError(f"NVIDIA chat completion API call failed: {exc}") from exc

            data = response.json()
            usage = data.get("usage") or {}
            record["prompt_tokens"] = usage.get("prompt_tokens")
            record["completion_tokens"] = usage.get("completion_tokens")
            record["total_tokens"] = usage.get("total_tokens")
            choices = data.get("choices") or []
            if choices and choices[0].get("message", {}).get("content"):
                return choices[0]["message"]["content"]
            raise RuntimeError(f"NVIDIA chat completion returned no content: {data}")

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> AsyncIterator[str]:
        selected_model = self.model_for(purpose, model_name)
        if not self._configured():
            if self.settings.environment == "test" or self.settings.disable_external_llm:
                yield self._offline_response(prompt)
                return
            raise RuntimeError("NVIDIA API is not configured. Please set NVIDIA_API_KEY in your environment/dotenv file.")

        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": self.settings.nvidia_max_tokens,
            "stream": True,
        }
        await self._rate_limiter.acquire()
        try:
            async with httpx.AsyncClient(timeout=self.settings.nvidia_request_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.settings.nvidia_base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    import json as _json

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk_raw = line[len("data:"):].strip()
                        if chunk_raw == "[DONE]":
                            break
                        try:
                            chunk = _json.loads(chunk_raw)
                        except _json.JSONDecodeError:
                            continue
                        delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
        except Exception as exc:
            if self.settings.environment == "test" or self.settings.disable_external_llm:
                yield self._offline_response(prompt)
                return
            raise RuntimeError(f"NVIDIA streaming API call failed: {exc}") from exc

    async def generate_with_image(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        *,
        purpose: LLMPurpose = "ocr",
        model_name: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        """Multimodal OCR / vision call via OpenAI-compatible image_url content."""
        selected_model = model_name or self.settings.nvidia_vision_model
        async with log_llm_call(self.name, "generate_with_image", purpose, selected_model) as record:
            if not self._configured():
                if self.settings.environment == "test" or self.settings.disable_external_llm:
                    return ""
                raise RuntimeError("NVIDIA API is not configured. Please set NVIDIA_API_KEY in your environment/dotenv file.")

            encoded = base64.b64encode(image_bytes).decode("ascii")
            data_url = f"data:{mime_type};base64,{encoded}"
            payload = {
                "model": selected_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            timeout = self.settings.ocr_request_timeout_seconds

            async def _call() -> httpx.Response:
                await self._rate_limiter.acquire()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{self.settings.nvidia_base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp

            try:
                retryer = build_retrying(self.settings.nvidia_max_retries)
                async for attempt in retryer:
                    with attempt:
                        record["retries"] = attempt.retry_state.attempt_number - 1
                        response = await _call()
            except Exception as exc:
                if self.settings.environment == "test" or self.settings.disable_external_llm:
                    return ""
                raise RuntimeError(f"NVIDIA vision OCR API call failed: {exc}") from exc

            data = response.json()
            usage = data.get("usage") or {}
            record["prompt_tokens"] = usage.get("prompt_tokens")
            record["completion_tokens"] = usage.get("completion_tokens")
            record["total_tokens"] = usage.get("total_tokens")
            choices = data.get("choices") or []
            if choices and choices[0].get("message", {}).get("content"):
                return choices[0]["message"]["content"]
            raise RuntimeError(f"NVIDIA vision OCR returned no content: {data}")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed_batch(texts, "passage")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed_batch([text], "query")
        return vectors[0] if vectors else []

    async def _embed_batch(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not texts:
            return []
        if not self._configured():
            if self.settings.environment == "test" or self.settings.disable_external_llm:
                return [self._hash_embedding(text) for text in texts]
            raise RuntimeError("NVIDIA API is not configured. Please set NVIDIA_API_KEY in your environment/dotenv file.")

        try:
            return await self._embed_call(texts, input_type)
        except (_TokenLimitExceeded, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code != 400:
                if self.settings.environment == "test" or self.settings.disable_external_llm:
                    return [self._hash_embedding(text) for text in texts]
                raise RuntimeError(f"NVIDIA embedding API call failed: {exc}") from exc
            # A 400 for the whole batch (token limit, or some other single bad
            # input — e.g. garbage text from a scanned/malformed PDF) means one
            # item is the problem, not all of them. Isolate per-text instead of
            # failing every chunk in the batch for one bad apple.
            return [await self._embed_one_with_shrink(text, input_type) for text in texts]
        except Exception as exc:
            if self.settings.environment == "test" or self.settings.disable_external_llm:
                return [self._hash_embedding(text) for text in texts]
            raise RuntimeError(f"NVIDIA embedding API call failed: {exc}") from exc

    async def _embed_one_with_shrink(self, text: str, input_type: str, max_attempts: int = 5) -> list[float]:
        current = text
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                vectors = await self._embed_call([current], input_type)
                return vectors[0]
            except _TokenLimitExceeded as exc:
                last_exc = exc
                current = current[: max(200, int(len(current) * 0.65))]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code != 400:
                    if self.settings.environment == "test" or self.settings.disable_external_llm:
                        return self._hash_embedding(text)
                    raise RuntimeError(f"NVIDIA embedding API call failed: {exc}") from exc
                # Non-token-limit 400 (e.g. malformed/garbage extracted text) —
                # shrinking sometimes helps if the issue is in a specific span;
                # if it doesn't, we give up on this one chunk below rather than
                # taking down the whole file's batch.
                current = current[: max(200, int(len(current) * 0.65))]
            except Exception as exc:
                if self.settings.environment == "test" or self.settings.disable_external_llm:
                    return self._hash_embedding(text)
                raise RuntimeError(f"NVIDIA embedding API call failed: {exc}") from exc
        try:
            vectors = await self._embed_call([current[:400]], input_type)
            return vectors[0]
        except Exception as exc:
            logger.warning(
                "nvidia_embed_chunk_skipped reason=%s text_preview=%r",
                repr(last_exc or exc), text[:80],
            )
            return self._hash_embedding(text)

    async def _embed_call(self, texts: list[str], input_type: str) -> list[list[float]]:
        payload = {
            "model": self.settings.nvidia_embedding_model,
            "input": texts,
            "input_type": input_type,
            "encoding_format": "float",
        }

        async def _call() -> httpx.Response:
            await self._rate_limiter.acquire()
            async with httpx.AsyncClient(timeout=self.settings.nvidia_embedding_timeout_seconds) as client:
                resp = await client.post(
                    f"{self.settings.nvidia_base_url}/embeddings",
                    headers=self._headers(),
                    json=payload,
                )
                if resp.status_code == 400 and "exceeds maximum allowed token size" in resp.text:
                    raise _TokenLimitExceeded(resp.text)
                resp.raise_for_status()
                return resp

        async with log_llm_call(self.name, "embed", input_type, self.settings.nvidia_embedding_model):
            retryer = build_retrying(self.settings.nvidia_max_retries)
            response = None
            async for attempt in retryer:
                with attempt:
                    response = await _call()
            data = response.json()

        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [[float(v) for v in item["embedding"]] for item in items]
        if len(vectors) != len(texts):
            raise RuntimeError(f"NVIDIA embedding count mismatch: sent {len(texts)}, got {len(vectors)}")
        return vectors

    def health_check(self) -> dict:
        if self.settings.disable_external_llm:
            return {"provider": self.name, "status": "disabled"}
        if not self.settings.nvidia_api_key:
            return {"provider": self.name, "status": "missing_key"}
        return {
            "provider": self.name,
            "status": "configured",
            "base_url": self.settings.nvidia_base_url,
            "reasoning_model": self.settings.nvidia_reasoning_model,
            "embedding_model": self.settings.nvidia_embedding_model,
        }

    def _offline_response(self, prompt: str) -> str:
        # Deliberately domain-neutral -- this used to hardcode health-
        # insurance vocabulary ("IRDAI health insurance guidelines",
        # "physician support letter", "GRO", "hospital"/"treatment" field
        # names) as the offline fallback for EVERY domain's agents, so a
        # telecom/banking/airlines/etc. case that ever hit this path (LLM
        # provider disabled/unreachable) would get back a fabricated
        # insurance regulator citation and insurance-shaped evidence fields
        # that don't apply to its actual domain. This path only exists so
        # the app doesn't hard-crash with no LLM connectivity -- it should
        # say exactly that, not invent domain-specific claims it has no way
        # to back up.
        lower = prompt.lower()
        if "return json" in lower and "research agent" in lower:
            return '{"applicable_clauses":[],"possible_exclusions":[],"waiting_periods":[],"regulations":[],"summary":"Offline fallback -- no LLM connectivity, so no real research was performed. Configure an LLM provider for real analysis.","confidence":0.0}'
        if "return json" in lower and "evidence agent" in lower:
            return '{"documents_missing":[],"key_dates":[],"summary":"Offline fallback -- no LLM connectivity, so no evidence extraction was performed."}'
        if "return json" in lower and "strategy agent" in lower:
            return '{"can_appeal":"UNKNOWN","success_probability":0.0,"recommended_strategy":"","evidence_required":[],"escalation_path":[],"summary":"Offline fallback -- no LLM connectivity, so no strategy was generated. Configure an LLM provider for a real recommendation."}'
        if "return json" in lower and "review agent" in lower:
            return '{"missing_evidence":[],"hallucination_risks":[],"wrong_clause_risks":[],"weak_arguments":[],"approval_ready":false,"summary":"Offline fallback -- no LLM connectivity, so nothing was reviewed. Do not treat this case as reviewed."}'
        if "appeal letter" in lower or "negotiation agent" in lower:
            return (
                '{"appeal_letter":"Offline placeholder -- no LLM connectivity, so no real appeal letter was drafted.",'
                '"complaint_email":"Offline placeholder -- no real complaint email was drafted.",'
                '"escalation_note":"Offline placeholder -- no real escalation note was drafted.",'
                '"consumer_complaint":"Offline placeholder -- no real regulator complaint was drafted.",'
                '"summary":"Offline fallback -- no LLM connectivity, so no documents were actually drafted."}'
            )
        if "final case report" in lower:
            return "Executive Summary: No LLM provider is currently reachable, so this case has not actually been analyzed. Configure NVIDIA_API_KEY (or another provider) and re-run for a real analysis."
        return "No LLM provider is currently reachable, so no real output was generated for this request."
