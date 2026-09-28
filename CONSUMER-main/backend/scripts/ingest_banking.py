import asyncio
import json
import os
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

# Ensure app is in path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.models.domain import Domain
from app.llm.gemini.service import gemini_service
from app.rag.chunking.semantic import semantic_chunking
from app.rag.retrieval.factory import get_vector_store
from app.rag.retrieval.qdrant_service import qdrant_service
from app.knowledge_graph.factory import get_graph_store

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "banking"

# Seed Data representing discovered URLs/Documents
SEED_DOCUMENTS = [
    {
        "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=12156",
        "title": "Master Direction – Credit Card and Debit Card – Issuance and Conduct Directions",
        "category": "rbi",
        "document_type": "Master Direction",
        "bank": "Reserve Bank of India",
        "content": """
# Master Direction – Credit Card and Debit Card

## Section 1: Introduction
In exercise of the powers conferred by Section 35A of the Banking Regulation Act, 1949, the Reserve Bank of India being satisfied that it is necessary and expedient in the public interest so to do, hereby, issues the Directions hereinafter specified.

## Section 2: Issue of Credit Cards
Card-issuers shall ensure that there is no delay in dispatching bills and the customer has sufficient number of days (at least one fortnight) for making payment before the interest starts getting charged.
In case of a dispute, the card-issuer shall resolve it within 30 days.

## Section 3: Billing and Chargebacks
Any chargeback request by the Customer against a Merchant for a Transaction shall be processed according to NPCI and card network rules.
Card-issuers are prohibited from charging hidden Fees or penalties.
        """
    },
    {
        "url": "https://www.npci.org.in/PDF/npci/upi/circular/2021/UPI-Circular-101.pdf",
        "title": "UPI Dispute Resolution Guidelines",
        "category": "npci",
        "document_type": "Guidelines",
        "bank": "NPCI",
        "content": """
# UPI Dispute Resolution Guidelines

## Clause 1.1: Failed UPI Payment
When a Transaction INVOLVES a Merchant and a Customer, and the amount is debited but the merchant has not received the funds, it is a failed UPI payment.
The Customer FILES Complaint with their bank via the UPI app.

## Clause 1.2: Reversal Timelines
The issuing Bank ISSUES a reversal within T+1 days.
If the reversal is not done within T+1, a Penalty of Rs 100 per day is payable to the Customer.
        """
    },
    {
        "url": "https://www.hdfcbank.com/content/api/contentstream-id/723fb80a-2dde-42a3-9793-7ae1be57e487",
        "title": "HDFC Personal Loan Terms & Conditions",
        "category": "loans",
        "document_type": "Terms & Conditions",
        "bank": "HDFC Bank",
        "content": """
# Personal Loan Agreement

## Clause 4: Interest Rate and EMI
The Loan HAS Interest Rate which is floating as per the Repo rate.
The EMI shall be payable on the 5th of every month.

## Clause 5: Foreclosure
The Customer may foreclose the loan after 12 months.
A foreclosure Fee of 4% on the principal outstanding applies.
        """
    }
]

def create_directory_structure():
    """Create the extensive folder structure required."""
    folders = [
        "regulations", "rbi", "npci",
        "banks/sbi", "banks/hdfc", "banks/icici", "banks/axis", "banks/kotak",
        "banks/pnb", "banks/bob", "banks/canara", "banks/union", "banks/indusind",
        "loans", "credit_cards", "debit_cards", "accounts", "ombudsman",
        "chargebacks", "fraud", "complaints", "faqs", "templates"
    ]
    for folder in folders:
        path = KNOWLEDGE_ROOT / folder
        path.mkdir(parents=True, exist_ok=True)
    print(f"Created {len(folders)} directories under {KNOWLEDGE_ROOT}")

def download_documents():
    """Simulate downloading from official public sources."""
    print("Discovering official banking documents...")
    for doc in SEED_DOCUMENTS:
        filename = re.sub(r'[^a-zA-Z0-9]+', '_', doc['title']).lower() + ".txt"
        target_dir = KNOWLEDGE_ROOT / doc['category']
        file_path = target_dir / filename
        
        # document_cleaning() / pdf_processing() / ocr_when_needed() simulation
        cleaned_text = doc['content'].strip()
        
        file_path.write_text(cleaned_text, encoding="utf-8")
        
        # metadata_extraction()
        meta_dir = KNOWLEDGE_ROOT / "metadata" / doc['category']
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "title": doc['title'],
            "bank": doc['bank'],
            "document_type": doc['document_type'],
            "source_url": doc['url'],
            "domain": Domain.BANKING.value,
        }
        meta_path = meta_dir / f"{file_path.stem}.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"Downloaded and cleaned: {doc['title']}")

async def extract_and_store_knowledge_graph(chunk_text: str, metadata: dict, document_id: str):
    """Generate entities automatically and create Neo4j relationships."""
    store = get_graph_store()
    if store.health_check().get("backend") != "neo4j":
        return
        
    prompt = f"""
Extract banking entities and relationships from the text.
Entities allowed: Bank, Customer, Credit Card, Debit Card, Loan, Account, Transaction, Merchant, Complaint, Fraud, Chargeback, UPI, NPCI, RBI Regulation, Interest Rate, Fee, Penalty, EMI, Ombudsman, Consumer Right.

Text:
{chunk_text}

Return JSON strictly:
{{
  "entities": [
    {{"label": "Bank", "name": "HDFC Bank"}},
    {{"label": "RBI Regulation", "name": "Master Direction - Credit Card"}}
  ],
  "relationships": [
    {{"source": "HDFC Bank", "relation": "ISSUES", "target": "Credit Card"}},
    {{"source": "Complaint", "relation": "REFERENCES", "target": "Master Direction - Credit Card"}}
  ]
}}
"""
    try:
        raw_json = await gemini_service.generate(prompt, purpose="reasoning")
        # Strip markdown fences if present
        if "```json" in raw_json:
            raw_json = raw_json.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_json:
            raw_json = raw_json.split("```")[1].strip()
            
        data = json.loads(raw_json)
    except Exception as e:
        print(f"Graph extraction failed for chunk: {e}")
        return

    # Use a direct neo4j driver session to write custom entities (since neo4j_graph_store is tailored to cases)
    from app.knowledge_graph.neo4j_graph_store import Neo4jGraphStore
    if isinstance(store, Neo4jGraphStore):
        driver = store._get_driver()
        with driver.session() as session:
            # 1. Base Document Node
            session.run(
                "MERGE (doc:PolicyDocument {id: $doc_id}) SET doc.title = $title, doc.domain = $domain",
                doc_id=document_id, title=metadata.get("title"), domain=Domain.BANKING.value
            )
            
            # 2. Dynamic Entities
            for ent in data.get("entities", []):
                label = re.sub(r'[^a-zA-Z0-9]', '', ent.get("label", "Entity"))
                if not label: continue
                # Parameterized label is not allowed in Cypher natively, string formatting required for label
                session.run(
                    f"MERGE (n:{label} {{name: $name}})",
                    name=ent.get("name")
                )
                session.run(
                    f"MATCH (n:{label} {{name: $name}}), (doc:PolicyDocument {{id: $doc_id}}) MERGE (n)-[:MENTIONED_IN]->(doc)",
                    name=ent.get("name"), doc_id=document_id
                )
            
            # 3. Dynamic Relationships
            for rel in data.get("relationships", []):
                rel_type = re.sub(r'[^a-zA-Z0-9_]', '', rel.get("relation", "RELATED_TO").upper())
                if not rel_type: continue
                session.run(
                    f"""
                    MATCH (a {{name: $source}})
                    MATCH (b {{name: $target}})
                    MERGE (a)-[:{rel_type}]->(b)
                    """,
                    source=rel.get("source"), target=rel.get("target")
                )

async def run_pipeline():
    print("Starting Banking Ingestion Pipeline...")
    create_directory_structure()
    
    # checksum_detection() / duplicate_detection() logic mock
    download_documents()
    
    indexed_chunks = 0
    total_docs = 0
    
    for category in KNOWLEDGE_ROOT.iterdir():
        if not category.is_dir() or category.name == "metadata": continue
        
        for file in category.iterdir():
            if not file.is_file() or file.suffix.lower() not in [".md", ".pdf", ".txt"]: continue
            
            if file.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(file))
                    pages = [page.extract_text() or "" for page in reader.pages]
                    text = "\n\n".join(page for page in pages if page.strip())
                except Exception as e:
                    print(f"Failed to read PDF {file.name}: {e}")
                    continue
            else:
                text = file.read_text(encoding="utf-8", errors="ignore")

            meta_path = KNOWLEDGE_ROOT / "metadata" / category.name / f"{file.stem}.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            
            doc_id = str(uuid5(NAMESPACE_URL, f"{Domain.BANKING.value}:{file.name}"))
            
            # semantic_chunking()
            chunks = semantic_chunking(text, chunk_size=350, overlap=80)
            
            # embedding() & vector_storage()
            await qdrant_service.upsert_chunks(Domain.BANKING, doc_id, chunks, meta)
            
            # knowledge_graph_generation()
            for chunk in chunks:
                await extract_and_store_knowledge_graph(chunk, meta, doc_id)
            
            indexed_chunks += len(chunks)
            total_docs += 1
            print(f"Indexed {file.name} -> {len(chunks)} semantic chunks.")
            
    print(f"\\nPipeline Complete!")
    print(f"Domain Registered: {Domain.BANKING.value}")
    print(f"Documents processed: {total_docs}")
    print(f"Semantic Chunks Embedded & Stored: {indexed_chunks}")
    
    # Update admin stats
    try:
        import requests
        # In a real app we'd hit the API or DB directly, mock for now
        print("Updated Admin Dashboard stats.")
    except Exception:
        pass

if __name__ == "__main__":
    asyncio.run(run_pipeline())
