from __future__ import annotations

from typing import AsyncIterator

from app.core.config import Settings
from app.llm.base import LLMProvider, LLMPurpose
from app.llm.observability import log_llm_call


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._configured = False

    @property
    def embedding_dimension(self) -> int:
        return self.settings.gemini_embedding_dimension

    def _configure(self) -> bool:
        if self._configured:
            return True
        if self.settings.disable_external_llm:
            return False
        if not self.settings.gemini_api_key:
            return False
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.settings.gemini_api_key)
            self._configured = True
            return True
        except Exception:
            return False

    def embedding_mode(self) -> str:
        if self._configure():
            return "gemini"
        if self.settings.environment == "test" or self.settings.disable_external_llm:
            return "hash_fallback"
        return "gemini"

    def model_for(self, purpose: LLMPurpose | None = None, model_name: str | None = None) -> str:
        if model_name:
            return model_name
        if purpose == "router":
            return self.settings.gemini_router_model
        if purpose == "planner":
            return self.settings.gemini_planner_model
        if purpose == "response":
            return self.settings.gemini_response_model
        if purpose == "summarization":
            return self.settings.gemini_summarization_model
        if purpose == "ocr":
            return self.settings.gemini_ocr_model
        return self.settings.gemini_reasoning_model  # covers reasoning + kg_extraction (no dedicated Gemini KG model)

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> str:
        selected_model = self.model_for(purpose, model_name)
        async with log_llm_call(self.name, "generate", purpose, selected_model) as record:
            if self._configure():
                try:
                    import google.generativeai as genai

                    model = genai.GenerativeModel(selected_model)
                    response = model.generate_content(
                        prompt,
                        generation_config={"temperature": temperature},
                    )
                    usage = getattr(response, "usage_metadata", None)
                    if usage is not None:
                        record["prompt_tokens"] = getattr(usage, "prompt_token_count", None)
                        record["completion_tokens"] = getattr(usage, "candidates_token_count", None)
                        record["total_tokens"] = getattr(usage, "total_token_count", None)
                    if response.text:
                        return response.text
                except Exception as exc:
                    if self.settings.environment != "test":
                        raise RuntimeError(f"Gemini generation API call failed: {exc}") from exc

            if self.settings.environment == "test" or self.settings.disable_external_llm:
                return self._offline_response(prompt)
            raise RuntimeError("Gemini API is not configured. Please set GEMINI_API_KEY in your environment/dotenv file.")

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> AsyncIterator[str]:
        selected_model = self.model_for(purpose, model_name)
        if self._configure():
            try:
                import google.generativeai as genai

                model = genai.GenerativeModel(selected_model)
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": temperature},
                    stream=True,
                )
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as exc:
                if self.settings.environment != "test":
                    raise RuntimeError(f"Gemini streaming API call failed: {exc}") from exc

        if self.settings.environment == "test" or self.settings.disable_external_llm:
            yield self._offline_response(prompt)
            return
        raise RuntimeError("Gemini API is not configured. Please set GEMINI_API_KEY in your environment/dotenv file.")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._configure():
            try:
                import google.generativeai as genai

                model = self.settings.embedding_model
                if not model.startswith(("models/", "tunedModels/")):
                    model = f"models/{model}"
                embeddings: list[list[float]] = []
                for start in range(0, len(texts), 1):
                    batch = texts[start:start + 1]
                    response = genai.embed_content(
                        model=model,
                        content=batch,
                        task_type="retrieval_document",
                        output_dimensionality=768,
                        request_options={"timeout": 60},
                    )
                    raw_embeddings = response.get("embedding") if isinstance(response, dict) else None
                    if raw_embeddings and isinstance(raw_embeddings[0], list):
                        embeddings.extend([[float(value) for value in item] for item in raw_embeddings])
                    elif raw_embeddings:
                        embeddings.append([float(value) for value in raw_embeddings])
                if len(embeddings) == len(texts):
                    return embeddings
            except Exception as exc:
                if self.settings.environment != "test":
                    raise RuntimeError(f"Gemini batch embedding API call failed: {exc}") from exc

        if self.settings.environment == "test" or self.settings.disable_external_llm:
            return [self._hash_embedding(text) for text in texts]
        raise RuntimeError("Gemini API is not configured. Please set GEMINI_API_KEY in your environment/dotenv file.")

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed(text, "retrieval_query")

    async def _embed(self, text: str, task_type: str) -> list[float]:
        if not text:
            return [0.0] * 768
        if self._configure():
            try:
                import google.generativeai as genai

                model = self.settings.embedding_model
                if not model.startswith(("models/", "tunedModels/")):
                    model = f"models/{model}"
                response = genai.embed_content(
                    model=model,
                    content=text,
                    task_type=task_type,
                    output_dimensionality=768,
                    request_options={"timeout": 60},
                )
                embedding = response.get("embedding") if isinstance(response, dict) else None
                if embedding:
                    return [float(value) for value in embedding]
            except Exception as exc:
                if self.settings.environment != "test":
                    raise RuntimeError(f"Gemini embedding API call failed: {exc}") from exc

        if self.settings.environment == "test" or self.settings.disable_external_llm:
            return self._hash_embedding(text)
        raise RuntimeError("Gemini API is not configured. Please set GEMINI_API_KEY in your environment/dotenv file.")

    def health_check(self) -> dict:
        if self.settings.disable_external_llm:
            return {"provider": self.name, "status": "disabled"}
        if not self.settings.gemini_api_key:
            return {"provider": self.name, "status": "missing_key"}
        return {"provider": self.name, "status": "configured", "reasoning_model": self.settings.gemini_reasoning_model}

    def _offline_response(self, prompt: str) -> str:
        # Deliberately domain-neutral -- see nvidia_provider.py's identical
        # method for the full explanation. This used to hardcode health-
        # insurance vocabulary as the offline fallback for every domain's
        # agents, so a telecom/banking/airlines/etc. case would get back a
        # fabricated insurance regulator citation and insurance-shaped
        # evidence fields that don't apply to its actual domain.
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
            return "Executive Summary: No LLM provider is currently reachable, so this case has not actually been analyzed. Configure GEMINI_API_KEY (or another provider) and re-run for a real analysis."
        return "No LLM provider is currently reachable, so no real output was generated for this request."
