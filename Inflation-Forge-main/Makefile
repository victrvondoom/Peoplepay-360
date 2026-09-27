SHELL := /bin/bash
PYTHON ?= python3
API_URL ?= http://127.0.0.1:8000
SIGNOZ_API_URL ?= http://127.0.0.1:8080
FOUNDRYCTL ?= $(shell command -v foundryctl 2>/dev/null || echo $$HOME/.local/bin/foundryctl)

.PHONY: install test demo demo-signoz sync health signoz-install signoz-bootstrap signoz-up signoz-down signoz-status signoz-key-check clean-artifacts

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	OTEL_EXPORTER_OTLP_ENDPOINT= INFLATIONFORGE_OTEL_EXPORTER=local $(PYTHON) -m pytest

demo:
	$(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

demo-signoz:
	OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 OTEL_SERVICE_NAME=inflationforge $(PYTHON) -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

sync:
	curl -sS -X POST $(API_URL)/api/prices/sync | $(PYTHON) -m json.tool

health:
	curl -sS $(API_URL)/health | $(PYTHON) -m json.tool

signoz-install:
	@test -x "$(FOUNDRYCTL)" || curl -fsSL https://signoz.io/foundry.sh | bash

signoz-bootstrap:
	$(PYTHON) scripts/bootstrap_signoz_env.py

signoz-up: signoz-bootstrap
	set -a && source .env && set +a && cd observability/signoz && $(FOUNDRYCTL) cast -f casting.yaml

signoz-down:
	cd observability/signoz/pours/deployment && docker compose down

signoz-status:
	@docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sed -n '1p;/signoz/p'

signoz-key-check:
	@set -a && source .env && set +a && test -n "$${SIGNOZ_API_KEY}" || (echo "Set SIGNOZ_API_KEY to a SigNoz service-account key." && false); \
	curl -fsS "$${SIGNOZ_API_URL}/api/v1/service_accounts/me" -H "SIGNOZ-API-KEY: $${SIGNOZ_API_KEY}" | \
	$(PYTHON) -c 'import json,sys; d=json.load(sys.stdin)["data"]; print("SigNoz API key valid:", d["name"], "| roles:", ", ".join(item["role"]["name"] for item in d.get("serviceAccountRoles", [])))'

clean-artifacts:
	@echo "InflationForge keeps an audit trail. Remove artifacts/inflationforge.db manually only if you intend to erase it."
