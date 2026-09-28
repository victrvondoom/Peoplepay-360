"""
Telecom Domain - Full Data Collection Script
Downloads real content from TRAI, DoT, Airtel, Jio, Vi, BSNL and stores
in the correct folder structure under knowledge/telecom/
"""
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "telecom"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ─────────────────────────────────────────────────────────────
# ALL SOURCES
# ─────────────────────────────────────────────────────────────
SOURCES = [
    # ── 1. TRAI ──────────────────────────────────────────────
    {
        "url": "https://www.trai.gov.in/regulations",
        "folder": "trai",
        "name": "trai_regulations_index",
        "title": "TRAI Regulations Index",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/notification",
        "folder": "trai",
        "name": "trai_notifications",
        "title": "TRAI Notifications",
        "authority": "TRAI",
    },
    {
        "url": "https://trai.gov.in/consumer-info/consumer-corner",
        "folder": "trai",
        "name": "trai_consumer_corner",
        "title": "TRAI Consumer Corner",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/consumer-info/broadband",
        "folder": "trai",
        "name": "trai_broadband_qos",
        "title": "TRAI Broadband Quality of Service",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/consumer-info/tariff",
        "folder": "trai",
        "name": "trai_tariff_info",
        "title": "TRAI Tariff Orders",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/consumer-info/mnp",
        "folder": "mnp",
        "name": "trai_mnp_info",
        "title": "TRAI Mobile Number Portability Guidelines",
        "authority": "TRAI",
    },
    # ── 2. DoT ───────────────────────────────────────────────
    {
        "url": "https://dot.gov.in/consumer-info/consumer-protection",
        "folder": "dot",
        "name": "dot_consumer_protection",
        "title": "DoT Consumer Protection Guidelines",
        "authority": "DoT",
    },
    {
        "url": "https://dot.gov.in/telecom-policies",
        "folder": "dot",
        "name": "dot_telecom_policies",
        "title": "DoT Telecom Policies",
        "authority": "DoT",
    },
    # ── 3. Airtel ─────────────────────────────────────────────
    {
        "url": "https://www.airtel.in/terms-and-conditions",
        "folder": "operators/airtel",
        "name": "airtel_terms",
        "title": "Airtel Terms and Conditions",
        "authority": "Airtel",
    },
    {
        "url": "https://www.airtel.in/prepaid/all-prepaid-plans",
        "folder": "operators/airtel",
        "name": "airtel_prepaid_plans",
        "title": "Airtel Prepaid Plans",
        "authority": "Airtel",
    },
    {
        "url": "https://www.airtel.in/airtel-broadband",
        "folder": "operators/airtel",
        "name": "airtel_broadband",
        "title": "Airtel Broadband Plans and Policies",
        "authority": "Airtel",
    },
    {
        "url": "https://www.airtel.in/airtel-xstream-fiber",
        "folder": "operators/airtel",
        "name": "airtel_fiber",
        "title": "Airtel Xstream Fiber Policies",
        "authority": "Airtel",
    },
    # ── 4. Jio ────────────────────────────────────────────────
    {
        "url": "https://www.jio.com/en-in/terms-and-conditions",
        "folder": "operators/jio",
        "name": "jio_terms",
        "title": "Jio Terms and Conditions",
        "authority": "Jio",
    },
    {
        "url": "https://www.jio.com/en-in/prepaid-data-plans",
        "folder": "operators/jio",
        "name": "jio_prepaid_plans",
        "title": "Jio Prepaid Recharge Plans",
        "authority": "Jio",
    },
    {
        "url": "https://www.jio.com/en-in/jio-fiber-plans",
        "folder": "operators/jio",
        "name": "jio_fiber",
        "title": "JioFiber Plans and Policies",
        "authority": "Jio",
    },
    # ── 5. Vi ─────────────────────────────────────────────────
    {
        "url": "https://www.myvi.in/terms-and-conditions",
        "folder": "operators/vi",
        "name": "vi_terms",
        "title": "Vi Terms and Conditions",
        "authority": "Vi",
    },
    {
        "url": "https://www.myvi.in/prepaid/all-prepaid-plans",
        "folder": "operators/vi",
        "name": "vi_prepaid_plans",
        "title": "Vi Prepaid Plans",
        "authority": "Vi",
    },
    # ── 6. BSNL ───────────────────────────────────────────────
    {
        "url": "https://www.bsnl.co.in/opencms/BSNL/BSNL/services/mobile/index.html",
        "folder": "operators/bsnl",
        "name": "bsnl_mobile_services",
        "title": "BSNL Mobile Services",
        "authority": "BSNL",
    },
    {
        "url": "https://www.bsnl.co.in/opencms/BSNL/BSNL/services/broadband/index.html",
        "folder": "operators/bsnl",
        "name": "bsnl_broadband",
        "title": "BSNL Broadband Policies",
        "authority": "BSNL",
    },
    # ── Wikipedia (rich structured overviews) ─────────────────
    {
        "url": "https://en.wikipedia.org/wiki/Telecom_Regulatory_Authority_of_India",
        "folder": "trai",
        "name": "trai_overview",
        "title": "TRAI Overview",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Airtel_(India)",
        "folder": "operators/airtel",
        "name": "airtel_overview",
        "title": "Airtel Company Overview",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Jio",
        "folder": "operators/jio",
        "name": "jio_overview",
        "title": "Jio Company Overview",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Vodafone_Idea",
        "folder": "operators/vi",
        "name": "vi_overview",
        "title": "Vi (Vodafone Idea) Overview",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/BSNL",
        "folder": "operators/bsnl",
        "name": "bsnl_overview",
        "title": "BSNL Overview",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Mobile_number_portability_in_India",
        "folder": "mnp",
        "name": "mnp_india_overview",
        "title": "Mobile Number Portability in India",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Department_of_Telecommunications",
        "folder": "dot",
        "name": "dot_overview",
        "title": "Department of Telecommunications Overview",
        "authority": "Wikipedia",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Telecom_Disputes_Settlement_and_Appellate_Tribunal",
        "folder": "regulations",
        "name": "tdsat_overview",
        "title": "TDSAT (Telecom Disputes Settlement Tribunal) Overview",
        "authority": "Wikipedia",
    },
    # ── Customer rights & billing topics ──────────────────────
    {
        "url": "https://en.wikipedia.org/wiki/Consumer_Protection_Act,_2019",
        "folder": "customer_rights",
        "name": "consumer_protection_act_2019",
        "title": "Consumer Protection Act 2019",
        "authority": "Wikipedia",
    },
    # ── OpenCSV airport data (OurAirports analogue for telecom) ─
    {
        "url": "https://consumerhelpline.gov.in",
        "folder": "complaints",
        "name": "national_consumer_helpline",
        "title": "National Consumer Helpline",
        "authority": "GoI",
    },
    # ── New sources (registry-verified, appended this session) ────────
    {
        "url": "https://sancharsaathi.gov.in/",
        "folder": "sanchar_saathi",
        "name": "sanchar_saathi_home",
        "title": "Sanchar Saathi Portal (Citizen Central Portal)",
        "authority": "DoT",
    },
    {
        "url": "https://sancharsaathi.gov.in/sfc/",
        "folder": "sanchar_saathi",
        "name": "sanchar_saathi_chakshu",
        "title": "Sanchar Saathi - Chakshu Suspected Fraud Communication Reporting",
        "authority": "DoT",
    },
    {
        "url": "https://trai.gov.in/tcccpr",
        "folder": "trai",
        "name": "trai_tcccpr_page",
        "title": "TCCCPR - Telecom Commercial Communications Customer Preference Regulations Page",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/sites/default/files/2024-09/RegulationUcc19072018.pdf",
        "folder": "trai",
        "name": "trai_tcccpr_2018_full_text",
        "title": "Telecom Commercial Communications Customer Preference Regulations, 2018 (Full Text)",
        "authority": "TRAI",
    },
    {
        "url": "http://trai.gov.in/node/3194",
        "folder": "trai",
        "name": "trai_qos_metering_billing_2023",
        "title": "Quality of Service (Code of Practice for Metering and Billing Accuracy) Regulations, 2023",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/release-publication/regulations",
        "folder": "trai",
        "name": "trai_regulations_index_2",
        "title": "TRAI Regulations Index",
        "authority": "TRAI",
    },
    {
        "url": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2102413",
        "folder": "trai",
        "name": "pib_tcccpr_amendment",
        "title": "TRAI Strengthens Consumer Protection with Amendments to TCCCPR, 2018",
        "authority": "PIB",
    },
    {
        "url": "https://trai.gov.in/preference-registration",
        "folder": "trai",
        "name": "trai_preference_registration",
        "title": "Customer Preference Registration Facility (NCPR / DND)",
        "authority": "TRAI",
    },
    {
        "url": "https://usof.gov.in/en/home",
        "folder": "usof",
        "name": "usof_home",
        "title": "Universal Service Obligation Fund / Digital Bharat Nidhi",
        "authority": "USOF",
    },
    {
        "url": "https://en.wikipedia.org/wiki/Do_Not_Disturb_Registry",
        "folder": "trai",
        "name": "wiki_dnd_registry",
        "title": "Do Not Disturb Registry",
        "authority": "Wikipedia",
    },
    {
        "url": "https://www.trai.gov.in/sites/default/files/2024-10/201208081218350931511Regulation23sep09%5b1%5d.pdf",
        "folder": "mnp",
        "name": "trai_mnp_regulations_2009_full_text",
        "title": "Telecommunication Mobile Number Portability Regulations, 2009 (Full Text)",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/sites/default/files/2024-09/Regulation_27012022.pdf",
        "folder": "trai",
        "name": "trai_tariff_order_amendment_2022",
        "title": "Telecommunication Tariff Order 1999 (Amendment, Jan 2022)",
        "authority": "TRAI",
    },
    {
        "url": "https://www.trai.gov.in/sites/default/files/2024-09/201211091141353328813Regulation20mar09%20(1).pdf",
        "folder": "trai",
        "name": "trai_qos_basic_cellular_2009",
        "title": "Standards of QoS of Basic Telephone (Wireline) and Cellular Mobile Telephone Service Regulations, 2009",
        "authority": "TRAI",
    },
    {
        "url": "http://www.trai.gov.in/telecom/qos",
        "folder": "trai",
        "name": "trai_qos_landing",
        "title": "TRAI Quality of Service Landing Page",
        "authority": "TRAI",
    },
]


def html_to_text(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(lines)


def save(folder: str, name: str, content: bytes, ext: str, metadata: dict):
    dest_dir = KNOWLEDGE_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filepath = dest_dir / f"{name}.{ext}"
    filepath.write_bytes(content)

    meta_dir = KNOWLEDGE_ROOT / "metadata" / folder
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{name}.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return filepath


def download(source: dict) -> bool:
    url = source["url"]
    folder = source["folder"]
    name = source["name"]
    title = source["title"]
    authority = source["authority"]
    print(f"  GET {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code not in (200, 301, 302):
            print(f"    -> HTTP {resp.status_code} — skipping")
            return False

        is_pdf = (
            url.lower().endswith(".pdf")
            or resp.headers.get("Content-Type", "").startswith("application/pdf")
        )

        if is_pdf:
            filepath = save(
                folder, name, resp.content, "pdf",
                {"title": title, "authority": authority, "source_url": url,
                 "domain": "telecom", "type": "pdf"}
            )
        else:
            # strip HTML → plain text for the AI pipeline
            text = html_to_text(resp.content)
            if len(text) < 200:
                print(f"    -> Too little content ({len(text)} chars) — skipping")
                return False
            filepath = save(
                folder, name, text.encode("utf-8"), "txt",
                {"title": title, "authority": authority, "source_url": url,
                 "domain": "telecom", "type": "html_text",
                 "raw_chars": len(text)}
            )

        size_kb = filepath.stat().st_size // 1024
        print(f"    -> Saved {size_kb} KB  =>  {filepath.relative_to(KNOWLEDGE_ROOT)}")
        return True

    except Exception as exc:
        print(f"    -> ERROR: {exc}")
        return False


def main():
    print("=" * 60)
    print("TELECOM DOMAIN — LIVE DATA DOWNLOAD")
    print("=" * 60)

    ok = fail = 0
    for src in SOURCES:
        success = download(src)
        if success:
            ok += 1
        else:
            fail += 1
        time.sleep(1)   # polite crawl delay

    print("=" * 60)
    print(f"Done.  Downloaded: {ok}   Failed: {fail}   Total: {ok+fail}")
    print("=" * 60)


if __name__ == "__main__":
    main()
