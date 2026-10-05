"""Refresh the ECHO-only CycloneDX inventory and OSV snapshot.

Run with `.venv-echo/Scripts/python.exe echo/scripts/refresh_supply_chain.py`.
The OSV query requires network access. This is not a full monorepo/container SBOM.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "extensions"
ENV = ROOT / ".venv-echo"


def main() -> None:
    distributions = {
        dist.metadata["Name"]: dist
        for dist in metadata.distributions()
        if dist.metadata.get("Name") and dist.metadata["Name"].lower() not in {"pip", "setuptools"}
    }
    canonical = {name.lower().replace("_", "-"): name for name in distributions}
    names = sorted(distributions, key=str.lower)
    versions = {name: distributions[name].version for name in names}
    refs = {name: f"pkg:pypi/{name.lower().replace('_', '-')}@{versions[name]}" for name in names}
    env = default_environment()
    env.update({"python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
                "python_full_version": sys.version.split()[0], "sys_platform": sys.platform,
                "platform_python_implementation": "CPython"})
    selected_extra = {"uvicorn": {"standard"}}
    deps: dict[str, set[str]] = {name: set() for name in names}
    for name in names:
        for raw in distributions[name].metadata.get_all("Requires-Dist") or []:
            try:
                req = Requirement(raw)
                dep_name = canonical.get(req.name.lower().replace("_", "-"))
                if dep_name and (not req.marker or req.marker.evaluate({**env, "extra": ""}) or
                                 any(req.marker.evaluate({**env, "extra": extra})
                                     for extra in selected_extra.get(name.lower(), set()))):
                    deps[name].add(dep_name)
            except Exception:
                continue

    def prop(name: str, value: str) -> dict[str, str]:
        return {"name": name, "value": value}

    components = []
    for name in names:
        dist = distributions[name]
        raw_license = (dist.metadata.get("License-Expression") or "").strip()
        classifiers = dist.metadata.get_all("Classifier") or []
        license_files = []
        for file in dist.files or []:
            if Path(str(file)).name.lower().startswith(("license", "copying", "notice")):
                path = Path(dist.locate_file(file))
                if path.is_file():
                    license_files.append({"path": str(path.resolve().relative_to(ROOT)),
                                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        c = {"type": "library", "bom-ref": refs[name], "name": name, "version": versions[name],
             "purl": refs[name], "scope": "optional" if name.lower() in {"pytest", "pytest-asyncio", "httpx"} else "required",
             "properties": [prop("echo:metadata:license-expression", raw_license or "NOASSERTION"),
                            prop("echo:metadata:license", (dist.metadata.get("License") or "NOASSERTION").strip() or "NOASSERTION"),
                            prop("echo:metadata:license-classifiers", json.dumps(classifiers)),
                            prop("echo:metadata:license-files", json.dumps(license_files)),
                            prop("echo:metadata:requires-dist", json.dumps(dist.metadata.get_all("Requires-Dist") or [])),
                            prop("echo:environment-role", "development" if name.lower() in {"pytest", "pytest-asyncio", "httpx"} else "runtime")]}
        if raw_license and all(ch.isalnum() or ch in ".-+() " for ch in raw_license):
            c["licenses"] = [{"expression": raw_license}]
        components.append(c)

    stamp = datetime.now(timezone.utc).isoformat()
    bom = {"$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json", "bomFormat": "CycloneDX",
           "specVersion": "1.6", "serialNumber": f"urn:uuid:{__import__('uuid').uuid4()}", "version": 1,
           "metadata": {"timestamp": stamp, "component": {"type": "application", "bom-ref": "peoplepay:echo:first-party",
             "name": "PeoplePay ECHO first-party core and adapters", "licenses": [{"license": {"name": "NOASSERTION"}}]},
             "properties": [prop("echo:inventory-source", "Installed .venv-echo importlib.metadata and local license files"),
                            prop("echo:inventory-scope", "Windows Python ECHO environment; not full monorepo, container, OS, dataset or model inventory"),
                            prop("echo:dependency-resolution", "Installed Requires-Dist active markers; uvicorn standard extra selected; pip/setuptools excluded as environment tools"),
                            prop("echo:advisory-scan", "OSV querybatch snapshot; see dependency-advisories.json"),
                            prop("echo:license-assessment", "Distribution metadata and installed license files; no legal interpretation or guessed SPDX for ambiguous metadata")]},
           "components": components,
           "dependencies": [{"ref": "peoplepay:echo:first-party", "dependsOn": [refs[n] for n in names if n.lower() in {"fastapi", "uvicorn", "falkordb", "pydantic", "pyyaml"}]},
                            *[{"ref": refs[n], "dependsOn": sorted(refs[d] for d in deps[n])} for n in names],
                            {"ref": "peoplepay:bundled:inflationforge", "dependsOn": []}]}
    queries = [{"version": versions[n], "package": {"name": n, "ecosystem": "PyPI"}} for n in names]
    req = urllib.request.Request("https://api.osv.dev/v1/querybatch", data=json.dumps({"queries": queries}).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
    response = json.load(urllib.request.urlopen(req, timeout=20))["results"]
    advisories = {"source": "OSV querybatch", "scanned_at": stamp, "environment": ".venv-echo",
                  "packages": [{"name": n, "version": versions[n],
                                "vulnerability_ids": sorted({v["id"] for v in row.get("vulns", [])})}
                               for n, row in zip(names, response, strict=True)]}
    (OUT / "sbom.json").write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
    (OUT / "dependency-advisories.json").write_text(json.dumps(advisories, indent=2) + "\n", encoding="utf-8")
    findings = [(p["name"], p["version"], p["vulnerability_ids"]) for p in advisories["packages"] if p["vulnerability_ids"]]
    print(json.dumps({"packages": len(names), "findings": findings, "scanned_at": stamp}, indent=2))


if __name__ == "__main__":
    main()
