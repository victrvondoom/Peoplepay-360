import os
import time
import json
import requests
from pathlib import Path
from duckduckgo_search import DDGS
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[1] / "knowledge" / "banking"

# Define the exact file structure needed
FOLDERS = [
    "rbi", "circulars", "ombudsman", "npci", 
    "banks/hdfc", "banks/icici", "banks/sbi", "banks/axis", 
    "cards", "loans", "upi", "chargebacks", "complaint_templates", "faqs"
]

# Queries to execute for filetype:pdf
SEARCH_TARGETS = [
    {
        "query": "RBI Master Direction Credit Card and Debit Card Issuance filetype:pdf",
        "category": "rbi",
        "bank": "Reserve Bank of India",
        "title_prefix": "RBI_Master_Direction_Credit_Card",
        "doc_type": "Master Direction"
    },
    {
        "query": "RBI Digital payment security controls filetype:pdf",
        "category": "rbi",
        "bank": "Reserve Bank of India",
        "title_prefix": "RBI_Digital_Payment_Security",
        "doc_type": "Master Direction"
    },
    {
        "query": "RBI Integrated Ombudsman Scheme 2021 filetype:pdf",
        "category": "ombudsman",
        "bank": "Reserve Bank of India",
        "title_prefix": "RBI_Ombudsman_Scheme",
        "doc_type": "Scheme Document"
    },
    {
        "query": "NPCI UPI dispute resolution guidelines filetype:pdf",
        "category": "npci",
        "bank": "NPCI",
        "title_prefix": "NPCI_UPI_Dispute_Guidelines",
        "doc_type": "Guidelines"
    },
    {
        "query": "HDFC Bank Credit Card Terms and Conditions filetype:pdf",
        "category": "banks/hdfc",
        "bank": "HDFC Bank",
        "title_prefix": "HDFC_Credit_Card_Terms",
        "doc_type": "Terms and Conditions"
    },
    {
        "query": "SBI Personal Loan Terms and Conditions filetype:pdf",
        "category": "banks/sbi",
        "bank": "SBI",
        "title_prefix": "SBI_Personal_Loan_Terms",
        "doc_type": "Terms and Conditions"
    },
    {
        "query": "ICICI Bank Savings Account Schedule of Charges filetype:pdf",
        "category": "banks/icici",
        "bank": "ICICI Bank",
        "title_prefix": "ICICI_Savings_Charges",
        "doc_type": "Fee Schedule"
    },
    {
        "query": "Axis Bank Auto Loan terms filetype:pdf",
        "category": "banks/axis",
        "bank": "Axis Bank",
        "title_prefix": "Axis_Auto_Loan_Terms",
        "doc_type": "Terms and Conditions"
    }
]

def ensure_directories():
    for folder in FOLDERS:
        (KNOWLEDGE_ROOT / folder).mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_ROOT / "metadata").mkdir(parents=True, exist_ok=True)

def download_pdf(url: str, filepath: Path) -> bool:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Very basic check to ensure it's a PDF
        if b"%PDF" in response.content[:1024]:
            filepath.write_bytes(response.content)
            return True
        else:
            logging.warning(f"URL did not return a valid PDF: {url}")
            return False
    except Exception as e:
        logging.error(f"Failed to download {url}: {e}")
        return False

def scrape_pdfs():
    ensure_directories()
    
    with DDGS() as ddgs:
        for target in SEARCH_TARGETS:
            logging.info(f"Searching for: {target['query']}")
            
            try:
                results = list(ddgs.text(target["query"], max_results=3))
            except Exception as e:
                logging.error(f"Search failed for {target['query']}: {e}")
                continue
                
            downloaded = False
            for result in results:
                url = result.get("href", "")
                if url.lower().endswith(".pdf") or "pdf" in url.lower():
                    logging.info(f"Attempting download: {url}")
                    
                    filename = f"{target['title_prefix']}.pdf"
                    target_dir = KNOWLEDGE_ROOT / target["category"]
                    filepath = target_dir / filename
                    
                    if download_pdf(url, filepath):
                        logging.info(f"Successfully downloaded {filename} to {target['category']}")
                        
                        # Generate Metadata
                        meta = {
                            "title": result.get("title", target["title_prefix"].replace("_", " ")),
                            "bank": target["bank"],
                            "category": target["category"],
                            "document_type": target["doc_type"],
                            "domain": "banking",
                            "source_url": url,
                            "original_snippet": result.get("body", "")
                        }
                        meta_dir = KNOWLEDGE_ROOT / "metadata" / target["category"]
                        meta_dir.mkdir(parents=True, exist_ok=True)
                        meta_path = meta_dir / f"{filepath.stem}.json"
                        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                        
                        downloaded = True
                        break # Move to next target after one successful download
                
                time.sleep(1) # Be polite to servers
                
            if not downloaded:
                logging.warning(f"Could not find or download a valid PDF for {target['title_prefix']}")

if __name__ == "__main__":
    logging.info(f"Starting Banking PDF Scraper to populate {KNOWLEDGE_ROOT}")
    scrape_pdfs()
    logging.info("Scraping completed.")
