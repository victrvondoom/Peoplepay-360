"""First-party synthetic providers for cross-extension contract demonstrations."""

from datetime import datetime, timezone

from echo.extensions.contracts import ExtensionRequest, ManifestAdapter, NormalizedResult
from echo.models import text_hash


class DemoSourceAdapter(ManifestAdapter):
    async def execute(self, request: ExtensionRequest) -> NormalizedResult:
        suffix = (request.context.requirement_id or "demo").replace("req-", "")
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc).isoformat()
        side_a = self.manifest.id == "demo-source-a"
        entities = [{"ref": name, "type": "Supplier", "name": f"Supplier {name.title()}",
                     "external_ids": {"official_domain": f"{name}-{suffix}.example"}}
                    for name in ("alpha", "beta", "gamma")]
        sources, evidence, dependencies = [], [], []
        claims = [{"ref": name + "-claim", "entity_ref": name, "predicate": "low_carbon_sourcing",
                   "value": True, "text": f"Synthetic {name} low-carbon sourcing observation",
                   "kind": "fact", "provenance_state": "KNOWN"}
                  for name in ("alpha", "beta", "gamma")]

        def source(ref: str, domain: str, path: str) -> None:
            excerpt = f"Synthetic fixture receipt: {ref}"
            sources.append({"ref": ref, "url": f"https://{domain}-{suffix}.example/{path}",
                            "publisher": f"Synthetic {domain}", "title": ref,
                            "source_type": "synthetic_demo", "provenance_state": "KNOWN",
                            "observed_at": now, "snapshot_text": excerpt, "content_hash": text_hash(excerpt)})

        def observation(ref: str, claim: str, source_ref: str) -> None:
            excerpt = f"Synthetic observation from {source_ref}"
            evidence.append({"ref": ref, "claim_ref": claim + "-claim", "source_ref": source_ref,
                             "excerpt": excerpt, "observed_at": now, "confidence": 0.9,
                             "content_hash": text_hash(excerpt), "provenance_state": "KNOWN"})

        source("alpha-root", "alpha", "original-release")
        indices = range(0, 4) if side_a else range(4, 8)
        for index in indices:
            ref = "alpha-root" if index == 0 else f"alpha-copy-{index}"
            if index:
                source(ref, f"publication-{index}", "alpha-story")
                dependencies.append({"from_source_ref": ref, "to_source_ref": "alpha-root",
                                     "type": ["DERIVED_FROM", "CITES", "MIRRORS"][index % 3],
                                     "explanation": "Explicit copied-release relationship in the synthetic fixture",
                                     "evidence_mode": "explicit", "confidence": 1.0})
            observation(f"alpha-observation-{index}", "alpha", ref)
        if not side_a:
            # Exact observation seen again by another extension: core must deduplicate it.
            observation("alpha-duplicate", "alpha", "alpha-root")
        for index in (range(1, 3) if side_a else [3]):
            ref = f"beta-root-{index}"
            source(ref, f"independent-lab-{index}", "beta-report")
            observation(f"beta-observation-{index}", "beta", ref)
        if side_a:
            source("gamma-root", "gamma", "disclosure")
            observation("gamma-observation", "gamma", "gamma-root")
        represented = {item["claim_ref"] for item in evidence}
        return NormalizedResult.model_validate({
            "extension_id": self.manifest.id, "extension_version": self.manifest.version,
            "sources": sources, "entities": entities,
            "claims": [claim for claim in claims if claim["ref"] in represented],
            "evidence": evidence, "source_dependencies": dependencies,
            "warnings": ["Synthetic fixture. No upstream open-source repository or supplier was contacted."],
        })
