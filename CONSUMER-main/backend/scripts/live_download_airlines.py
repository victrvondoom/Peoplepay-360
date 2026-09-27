import os
import time
import requests
from pathlib import Path
from urllib.parse import urlparse
import json

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "airlines"

FOLDERS = [
    "dgca", "ministry", "airsewa", "iata", "icao", "bcas", "airports",
    "airlines/air_india", "airlines/indigo", "airlines/spicejet",
    "airlines/akasa", "airlines/air_india_express", "airlines/alliance_air",
    "baggage", "refunds", "compensation", "complaints",
    "travel_insurance", "airport_data", "faqs", "templates", "synthetic_cases"
]

# Real URLs that we will actively perform GET requests against
LIVE_DOWNLOAD_TASKS = [
    {
        "url": "https://raw.githubusercontent.com/rakeshselvaraj0108/Proxy/main/README.md", # Placeholder to prove live download works, we will use real ones below
        "path": "test/test.txt",
        "title": "Test"
    },
    {
        "url": "https://www.iata.org/contentassets/fb1137ff561a4819a2d38f3db7308758/mc99-full-text.pdf",
        "path": "iata/montreal_convention.pdf",
        "title": "Montreal Convention 1999"
    },
    {
        "url": "https://www.bcasindia.gov.in/upload/uploadfiles/files/Civil%20Aviation%20Security%20Rules%202022.pdf",
        "path": "bcas/security_rules_2022.pdf",
        "title": "BCAS Security Rules"
    },
    {
        "url": "https://ncdrc.nic.in/bare_acts/Consumer%20Protection%20Act-1986.html",
        "path": "complaints/consumer_protection_act.html",
        "title": "Consumer Protection Act"
    },
    {
        "url": "https://en.wikipedia.org/wiki/Directorate_General_of_Civil_Aviation_(India)",
        "path": "dgca/dgca_overview.html",
        "title": "DGCA Overview"
    },
    {
        "url": "https://en.wikipedia.org/wiki/Air_India",
        "path": "airlines/air_india/overview.html",
        "title": "Air India Overview"
    },
    {
        "url": "https://en.wikipedia.org/wiki/IndiGo",
        "path": "airlines/indigo/overview.html",
        "title": "IndiGo Overview"
    },
    {
        "url": "https://en.wikipedia.org/wiki/SpiceJet",
        "path": "airlines/spicejet/overview.html",
        "title": "SpiceJet Overview"
    },
    {
        "url": "https://en.wikipedia.org/wiki/Indira_Gandhi_International_Airport",
        "path": "airports/delhi_airport.html",
        "title": "Delhi International Airport"
    },
    {
        "url": "https://en.wikipedia.org/wiki/Chhatrapati_Shivaji_Maharaj_International_Airport",
        "path": "airports/mumbai_airport.html",
        "title": "Mumbai International Airport"
    }
]

def ensure_folders():
    for folder in FOLDERS:
        (KNOWLEDGE_ROOT / folder).mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_ROOT / "metadata").mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_ROOT / "test").mkdir(parents=True, exist_ok=True)

def download_file(url, target_path, title):
    print(f"Executing LIVE HTTP GET: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        # If site blocks us (e.g. 403 Forbidden), print a warning and skip
        if response.status_code != 200:
            print(f"  [ERROR] Server returned {response.status_code}. Skipping.")
            return False
            
        file_path = KNOWLEDGE_ROOT / target_path
        
        # Save raw binary content (PDF or HTML)
        file_path.write_bytes(response.content)
        
        # Determine category from path
        category = target_path.split("/")[0]
        if "airlines/" in target_path:
            category = "/".join(target_path.split("/")[:2])
            
        # Write metadata
        meta = {
            "title": title,
            "category": category,
            "source_url": url,
            "domain": "airlines",
            "document_type": "pdf" if url.endswith(".pdf") else "html"
        }
        
        meta_dir = KNOWLEDGE_ROOT / "metadata" / category
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / f"{file_path.stem}.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        
        print(f"  -> Successfully downloaded {len(response.content)} bytes to {file_path}")
        return True
        
    except Exception as e:
        print(f"  [ERROR] Failed to download {url}: {e}")
        return False

def main():
    print("==================================================")
    print("LIVE INTERNET DOWNLOADER INITIATED")
    print("==================================================")
    ensure_folders()
    
    success_count = 0
    for task in LIVE_DOWNLOAD_TASKS:
        if download_file(task["url"], task["path"], task["title"]):
            success_count += 1
        time.sleep(1) # Polite delay
        
    print("==================================================")
    print(f"Successfully downloaded {success_count}/{len(LIVE_DOWNLOAD_TASKS)} files LIVE from the internet.")

if __name__ == "__main__":
    main()
