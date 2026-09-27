from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal

LLMPurpose = Literal["reasoning", "router", "planner", "response", "summarization", "ocr", "kg_extraction"]
EmbeddingPurpose = Literal["document", "query"]


class LLMProvider(ABC):
    """Provider-agnostic interface every LLM backend (Gemini, NVIDIA NIM, ...) implements.

    Agents and specialists depend on this interface, never on a concrete provider,
    so swapping LLM_PROVIDER in settings changes every call site at once.
    """

    name: str

    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Vector size this provider's configured embedding model produces."""

    @abstractmethod
    def model_for(self, purpose: LLMPurpose | None = None, model_name: str | None = None) -> str:
        """Resolve which underlying model id serves a given purpose."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.2,
        purpose: LLMPurpose = "reasoning",
        model_name: str | None = None,
    ) -> AsyncIterator[str]:
        ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embedding_mode(self) -> str:
        """Human-readable mode: e.g. 'gemini', 'nvidia', or 'hash_fallback'."""

    @abstractmethod
    def health_check(self) -> dict:
        ...

    async def embed_document(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0] if vectors else []

    async def embed(self, text: str, purpose: EmbeddingPurpose = "document") -> list[float]:
        if purpose == "query":
            return await self.embed_query(text)
        return await self.embed_document(text)

    async def summarize(self, text: str, instruction: str = "Summarize the retrieved evidence.") -> str:
        prompt = f"{instruction}\n\nText:\n{text[:12000]}"
        return await self.generate(prompt, temperature=0.1, purpose="summarization")

    def _hash_embedding(self, text: str, dimensions: int | None = None) -> list[float]:
        # Default to this provider's real embedding dimension (not a fixed 768)
        # so dev/test hash-fallback vectors are never silently the wrong size
        # for whichever provider produced them.
        size = dimensions if dimensions is not None else self.embedding_dimension
        seed = sum(ord(ch) for ch in text)
        return [((seed + index * 31) % 997) / 997 for index in range(size)]
