import os

# Set environment to test before any imports load settings
os.environ["ENVIRONMENT"] = "test"
os.environ["DISABLE_EXTERNAL_LLM"] = "true"
# Pin the default provider so existing tests are hermetic regardless of the
# developer's local .env LLM_PROVIDER choice; provider-specific behavior is
# covered explicitly in test_llm_providers.py. NVIDIA is the real active
# production provider (all reindexed knowledge-base collections are
# 1024-dim NVIDIA embeddings) — pinning tests to it too keeps the hash-fallback
# dimension used in test mode consistent with what's actually indexed.
os.environ.setdefault("LLM_PROVIDER", "nvidia")
