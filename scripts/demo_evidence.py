"""One offline entrypoint: validate claims, run checks, demonstrate revision-aware AI routing.

Receipts are content-bound observations, not signatures or live-provider certificates.
No credentials, external calls, payment execution or production services are needed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"measured", "simulated", "mock-verified", "live-verified", "unverified", "blocked"}
SUITES = ["packages/peoplepay-hypergrid/tests", "packages/peoplepay-model-gateway/tests",
          "payment/tests", "tests/test_platform_runtime.py", "tests/test_platform_workflow.py",
          "tests/test_demo_evidence.py"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(data, root=ROOT):
    if data.get("schema_version") != 1 or not data.get("claims"):
        raise ValueError("nonempty schema_version 1 manifest required")
    ids = set()
    for row in data["claims"]:
        if not row.get("id") or row["id"] in ids or row.get("status") not in STATUSES:
            raise ValueError("duplicate ID or unknown status")
        ids.add(row["id"])
        if not row.get("claim") or not row.get("boundary") or not row.get("sources"):
            raise ValueError("claim, boundary and sources required")
        for source in row["sources"]:
            path = (root / source).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f"invalid evidence source: {source}")
        # A checked-in label alone cannot certify a live integration. This offline
        # workflow deliberately refuses that promotion; use a separate reviewed live run.
        if row["status"] == "live-verified":
            raise ValueError("offline workflow cannot attest live verification")
    return data


def render_table(data):
    def cell(value):
        return value.replace("|", "\\|").replace("\n", " ")
    lines = ["# Claim-by-claim evidence", "",
             f"Audited baseline: `{data['audited_commit']}`. Labels describe the stated boundary; source presence alone is not proof. See [demo guide](README.md) and run receipt for current checks.", "",
             "| ID | Claim | Status | Evidence | Boundary |", "|---|---|---|---|---|"]
    for row in data["claims"]:
        sources = "; ".join(f"[{p}](../../{p})" for p in row["sources"])
        lines.append("| " + " | ".join(cell(x) for x in (row["id"], row["claim"], row["status"], sources, row["boundary"])) + " |")
    return "\n".join(lines) + "\n"


def source_hashes(data, root=ROOT):
    # Includes dependency/runtime/test code, not only files named in the claims.
    paths = {p for row in data["claims"] for p in row["sources"]}
    for prefix in ("packages", "payment", "shared", "journey", "gateway", "tests", "scripts"):
        paths.update(str(p.relative_to(root)) for p in (root / prefix).rglob("*.py") if "__pycache__" not in p.parts)
    paths.update(("pytest.ini", "docs/evidence/claims.json"))
    paths.update(str(p.relative_to(root)) for p in (root / "docs/evidence").glob("*.md"))
    paths.update(str(p.relative_to(root)) for p in (root / ".github/workflows").glob("*.yml"))
    return {p: digest(root / p) for p in sorted(paths)}


def revision_demo():
    # Import lazily: manifest validation needs only the standard library.
    for package in ("peoplepay-hypergrid", "peoplepay-model-gateway"):
        sys.path.insert(0, str(ROOT / "packages" / package / "src"))
    from hypergrid.corpus import T0, LAST_PERIOD, build_world
    from hypergrid.incremental import IncrementalEngine
    from hypergrid.routing import Config, Router
    from hypergrid.vintage import Observation

    store, requirements, series = build_world(80, n_synthetic=24, repeat_rate=0.3)
    engine = IncrementalEngine(store, requirements, draws=100)
    engine.full_run(T0 + .5)
    router = Router(Config("demo", "adaptive", "compact", det_first=True, cache=True, validate_escalate=True))
    before = [router.explain(r, d) for r, d in zip(requirements, engine.results)]
    used = next(s for s in series if engine.rev.get(store.key(s, LAST_PERIOD)))
    old = store.as_of(used, LAST_PERIOD, T0 + .5)
    store.append(Observation(used, LAST_PERIOD, old.value * 1.05, known_at=T0 + 1,
                             root_id=old.root_id, quality=old.quality, origin="SYNTHETIC"))
    impact = engine.apply_revisions([(used, LAST_PERIOD)], T0 + 1)
    exact, mismatches = engine.verify_against_full()
    # Re-explain only changed summaries, preserving all unaffected explanations.
    after = list(before)
    for i in impact.changed_ids:
        after[i] = router.explain(requirements[i], engine.results[i])
    if not exact or any(o.privacy_violation or not o.verified for o in after):
        raise ValueError("revision demo invariant failed")
    return {"mode": "offline simulation; no real LLM or payment", "decisions": len(requirements),
            "impact": asdict(impact), "exact_vs_full": exact, "mismatches": mismatches,
            "reexplained": len(impact.changed_ids),
            "simulated_calls_initial": sum(len(o.calls) for o in before),
            "simulated_calls_revision": sum(len(after[i].calls) for i in impact.changed_ids),
            "validator_accepted": sum(o.verified for o in after),
            "synthetic_oracle_correct": sum(o.correct for o in after),
            "boundary": "Validator acceptance is not factual correctness. Oracle uses synthetic known truth only; no calibrated accuracy claim. Outputs are advisory, not payment approvals."}


def run_checks(root=ROOT):
    with tempfile.TemporaryDirectory() as directory:
        junit = Path(directory) / "checks.xml"
        command = [sys.executable, "-m", "pytest", *SUITES, "-q", f"--junitxml={junit}"]
        run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=300)
        counts = {k: 0 for k in ("tests", "failures", "errors", "skipped")}
        if junit.exists():
            for suite in ET.parse(junit).getroot().iter("testsuite"):
                for k in counts:
                    counts[k] += int(suite.get(k, 0))
        # Never publish captured stdout, env or secrets in the receipt.
        return {"command": ["python", *command[1:-1]], "exit_code": run.returncode, **counts,
                "passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate manifest and generated table only; does not certify tests")
    parser.add_argument("--out", type=Path, default=ROOT / "demo-evidence.json")
    args = parser.parse_args(argv)
    data = validate_manifest(json.loads((ROOT / "docs/evidence/claims.json").read_text()))
    table = render_table(data)
    target = ROOT / "docs/evidence/CLAIMS.md"
    if args.check:
        if not target.exists() or target.read_text() != table:
            raise ValueError("claim table stale; regenerate with python scripts/demo_evidence.py")
        print("manifest and table consistent; no runtime or live verification performed")
        return 0
    target.write_text(table, encoding="utf-8")
    before = source_hashes(data)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    checks = run_checks()
    demo, error = None, None
    try:
        demo = revision_demo()
    except Exception as exc:
        error = type(exc).__name__  # do not export arbitrary exception messages
    after = source_hashes(data)
    ok = checks["exit_code"] == 0 and checks["passed"] > 0 and demo is not None and before == after
    receipt = {"schema_version": 1, "run_at_utc": datetime.now(timezone.utc).isoformat(),
               "git_head_at_run": revision, "python": sys.version.split()[0], "source_sha256": before,
               "source_stable_during_run": before == after, "checks": checks,
               "demo": demo, "demo_error": error, "offline_demo_checks_passed": ok,
               "live_verified": False, "production_ready": False,
               "boundary": "Pass covers named offline suites and this synthetic demo only. Hashes bind content, not authorship or external truth. Payment HTTP, ECHO integration and cloud deployment are excluded."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(args.out), "checks": checks, "offline_demo_checks_passed": ok, "demo_error": error}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
