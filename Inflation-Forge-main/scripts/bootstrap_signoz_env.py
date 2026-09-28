"""Create local-only SigNoz bootstrap credentials without exposing their values."""

from __future__ import annotations

import os
from pathlib import Path
import secrets


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


def current_value(text: str, key: str) -> str:
    prefix = f"{key}="
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def upsert(text: str, key: str, value: str) -> str:
    prefix = f"{key}="
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            break
    else:
        lines.append(f"{prefix}{value}")
    return "\n".join(lines) + "\n"


def main() -> None:
    text = ENV_PATH.read_text() if ENV_PATH.exists() else EXAMPLE_PATH.read_text()
    defaults = {
        "SIGNOZ_TOKENIZER_JWT_SECRET": secrets.token_hex(32),
        "SIGNOZ_ROOT_EMAIL": "inflationforge@local.dev",
        "SIGNOZ_ROOT_PASSWORD": f"If!9{secrets.token_hex(20)}Z",
        "SIGNOZ_ROOT_ORG_NAME": "InflationForge",
    }
    changed = False
    for key, fallback in defaults.items():
        if not current_value(text, key):
            text = upsert(text, key, fallback)
            changed = True

    if changed or not ENV_PATH.exists():
        temporary = ENV_PATH.with_suffix(".env.tmp")
        temporary.write_text(text)
        os.chmod(temporary, 0o600)
        temporary.replace(ENV_PATH)
    else:
        os.chmod(ENV_PATH, 0o600)
    print("SigNoz bootstrap environment ready (secret values were not printed).")


if __name__ == "__main__":
    main()
