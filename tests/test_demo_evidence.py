"""Negative evidence tests: missing proof, false promotion and stale revision data."""
import copy
import json
from pathlib import Path

import pytest

from scripts.demo_evidence import ROOT, render_table, revision_demo, source_hashes, validate_manifest


def manifest():
    return json.loads((ROOT / "docs/evidence/claims.json").read_text())


@pytest.mark.parametrize("mutation", ["status", "duplicate", "missing", "escape", "live", "empty"])
def test_manifest_refuses_unsubstantiated_or_malformed_evidence(mutation):
    data = copy.deepcopy(manifest())
    row = data["claims"][0]
    if mutation == "status": row["status"] = "production-ready"
    if mutation == "duplicate": data["claims"].append(copy.deepcopy(row))
    if mutation == "missing": row["sources"] = ["no-such-proof.json"]
    if mutation == "escape": row["sources"] = ["../outside.txt"]
    if mutation == "live": row["status"] = "live-verified"
    if mutation == "empty": data["claims"] = []
    with pytest.raises(ValueError):
        validate_manifest(data)


def test_claim_table_matches_canonical_manifest():
    data = validate_manifest(manifest())
    assert (ROOT / "docs/evidence/CLAIMS.md").read_text() == render_table(data)
    assert len(source_hashes(data)) > len(data["claims"])


def test_changed_code_changes_evidence_digest(tmp_path):
    from scripts.demo_evidence import digest
    path = tmp_path / "source.py"
    path.write_text("original")
    before = digest(path)
    path.write_text("changed")
    assert digest(path) != before


def test_central_demo_revises_only_impacted_decisions_and_labels_simulation():
    out = revision_demo()
    assert out["exact_vs_full"] and not out["mismatches"]
    assert 0 < out["impact"]["recomputed"] < out["decisions"]
    assert out["reexplained"] == out["impact"]["summary_changed"]
    assert out["reexplained"] <= out["impact"]["recomputed"]
    assert out["validator_accepted"] == out["decisions"]
    assert out["synthetic_oracle_correct"] <= out["validator_accepted"]
    assert "no real LLM" in out["mode"]
