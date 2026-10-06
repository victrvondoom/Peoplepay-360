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


import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_working_directory():
    """Relative fallback stores must never write into bundled datasets."""
    with tempfile.TemporaryDirectory(prefix="proxy-tests-") as directory:
        patches = pytest.MonkeyPatch()
        patches.chdir(directory)
        # Collection imports the application's singleton before fixtures run.
        # Rebind its store and caches after entering the temporary directory;
        # otherwise a single test relies on earlier tests to create its folder.
        from app.database.postgres.repositories import LocalRepositoryStore, case_repository
        patches.setattr(case_repository, "local", LocalRepositoryStore())
        for name in ("_cases", "_documents", "_agent_runs", "_appeals", "_knowledge_sources", "_knowledge_chunks"):
            patches.setattr(case_repository, name, {})
        patches.setattr(case_repository, "_events", [])
        try:
            yield
        finally:
            patches.undo()
