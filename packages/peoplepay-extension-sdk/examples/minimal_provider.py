"""Illustrative provider object; the host must explicitly review/register it."""

from datetime import datetime, timezone

from peoplepay_sdk import Capability, ExtensionHealth, ExtensionMetadata, ExtensionRequest, ExtensionResult


class CatalogExample:
    def metadata(self) -> ExtensionMetadata:
        return ExtensionMetadata(
            id="catalog-example",
            name="Catalog example",
            version="1.0.0",
            description="Illustrates the SDK without accessing an external catalog.",
            capabilities=[Capability(name="catalog_search", description="Search a catalog")],
        )

    def capabilities(self) -> list[Capability]:
        return self.metadata().capabilities

    async def health(self) -> ExtensionHealth:
        return ExtensionHealth(
            extension_id="catalog-example",
            status="healthy",
            checked_at=datetime.now(timezone.utc),
        )

    async def execute(self, request: ExtensionRequest) -> ExtensionResult:
        # No sample hits are fabricated when no catalog backend is configured.
        return ExtensionResult(
            request_id=request.request_id,
            extension_id="catalog-example",
            extension_version="1.0.0",
            status="partial",
            warnings=["No catalog backend is configured."],
        )
