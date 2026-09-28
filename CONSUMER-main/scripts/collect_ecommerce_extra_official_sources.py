from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from collect_ecommerce_official_sources import KNOWLEDGE_ROOT, ROOT, Source, download
import requests

EXTRA_SOURCES = [
    Source("India Code", "Consumer Protection Act 2019", "https://www.indiacode.nic.in/handle/123456789/15256", "official/india_code", "consumer_protection", "consumer_protection_act_2019_india_code"),
    Source("Department of Financial Services", "Digital Payments", "https://financialservices.gov.in/beta/en/page/digital-payments", "official/payment", "digital_payments", "dfs_digital_payments"),
    Source("Cashless India", "Mobile Wallets", "http://cashlessindia.gov.in/mobile_wallets.html", "official/payment", "digital_wallets", "cashless_india_mobile_wallets"),
    Source("NPCI", "IMPS Product Overview", "https://www.npci.org.in/what-we-do/imps/product-overview", "official/payment", "imps", "npci_imps_overview"),
    Source("NCH", "NCH Privacy Policy", "https://consumerhelpline.gov.in/public/privacypolicy", "official/nch", "privacy", "nch_privacy_policy"),
    Source("NCH", "NCH Contact", "https://consumerhelpline.gov.in/public/contact", "official/nch", "complaint_redressal", "nch_contact"),
]


def main() -> None:
    results = []
    with requests.Session() as session:
        for source in EXTRA_SOURCES:
            print(f"GET {source.authority}: {source.title}", flush=True)
            result = download(session, source, 0.25)
            print(f"  {result['status']} saved={len(result['saved'])} errors={len(result['errors'])}", flush=True)
            results.append(result)
            time.sleep(0.25)
    report_path = KNOWLEDGE_ROOT / "ecommerce_extra_official_download_report.json"
    report = {
        "domain": "ecommerce",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_sources": [asdict(source) for source in EXTRA_SOURCES],
        "download_results": results,
        "sources_attempted": len(EXTRA_SOURCES),
        "sources_downloaded": sum(1 for item in results if item["status"] == "ok"),
        "files_saved": sum(len(item["saved"]) for item in results),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "sources_attempted": report["sources_attempted"],
        "sources_downloaded": report["sources_downloaded"],
        "files_saved": report["files_saved"],
        "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
    }, indent=2))


if __name__ == "__main__":
    main()
