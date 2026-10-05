"""Fail if a path tracked at the pre-unification commit is absent now."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASELINE = "634dd3db73586076bf92648d7e6c32b6260fc9eb"


def git(*args: str) -> list[str]:
    completed = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return completed.stdout.splitlines()


def main() -> int:
    original = set(git("ls-tree", "-r", "--name-only", BASELINE))
    present = set(git("ls-files"))
    missing_from_index = original - present
    missing_from_worktree = {path for path in original if not Path(path).exists()}
    removed = sorted(missing_from_index | missing_from_worktree)
    print(f"Baseline paths: {len(original)}; currently tracked: {len(present)}; missing from worktree: {len(missing_from_worktree)}")
    if removed:
        print("Baseline paths missing from the index or worktree:", file=sys.stderr)
        print("\n".join(removed), file=sys.stderr)
        return 1
    print("Zero-deletion check passed. Existing paths may still have modifications; run the project test matrix for behavior.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
