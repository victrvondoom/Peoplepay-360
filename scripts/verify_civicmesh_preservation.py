"""Check pre-integration tracked paths and exact supplied CivicMesh bytes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    baseline = json.loads((ROOT / "docs/integration/civicmesh-preservation-baseline.json").read_text(encoding="utf-8"))
    missing = [path for path in baseline["tracked_paths"] if not (ROOT / path).is_file()]
    changed = [path for path, fingerprint in baseline["civicmesh_files"].items()
               if not (ROOT / path).is_file() or hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != fingerprint]
    print(f"Pre-CivicMesh tracked paths: {len(baseline['tracked_paths'])}; missing: {len(missing)}")
    print(f"Original CivicMesh files: {len(baseline['civicmesh_files'])}; missing or changed: {len(changed)}")
    if missing or changed:
        print("\n".join(missing + changed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
