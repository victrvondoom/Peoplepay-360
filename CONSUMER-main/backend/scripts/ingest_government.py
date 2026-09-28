"""
Government domain ingestion pipeline.
Reads all files under knowledge/government/, semantic-chunks them,
embeds and stores in Qdrant, and extracts KG entities to Neo4j.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.domain import Domain
from app.llm.gemini.service import gemini_service
from app.rag.chunking.semantic import semantic_chunking
from app.rag.retrieval.qdrant_service import qdrant_service
from app.knowledge_graph.factory import get_graph_store

KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge" / "government"
DOMAIN = Domain.GOVERNMENT
SKIP_DIRS = {"metadata", "chunks", "knowledge_graph"}

GOVERNMENT_ENTITY_LABELS = (
    "Citizen, Government Department, Ministry, Scheme, Service, Application, Certificate, "
    "Passport, Aadhaar, PAN, Driving Licence, Property Registration, Pension, RTI Request, "
    "Grievance, Appeal, Government Rule, Circular, Office, Timeline, Resolution"
)


def read_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(f"  PDF read error {path.name}: {e}")
            return ""
    elif ext == ".html":
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(path.read_bytes(), "html.parser")
            for t in soup(["script", "style"]):
                t.decompose()
            return soup.get_text(separator=" ", strip=True)
        except Exception as e:
            print(f"  HTML read error {path.name}: {e}")
            return ""
    else:
        return path.read_text(encoding="utf-8", errors="ignore")


async def extract_kg(chunk: str, meta: dict, doc_id: str):
    store = get_graph_store()
    if store.health_check().get("backend") != "neo4j":
        return
    prompt = f"""Extract government citizen-services entities and relationships from this text.
Entities: {GOVERNMENT_ENTITY_LABELS}.

Text: {chunk[:1500]}

Return ONLY valid JSON:
{{"entities":[{{"label":"Government Department","name":"UIDAI"}}],
  "relationships":[{{"source":"Aadhaar","relation":"ISSUED_BY","target":"UIDAI"}}]}}"""
    try:
        raw = await gemini_service.generate(prompt, purpose="reasoning")
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].strip()
        data = json.loads(raw)
    except Exception:
        return

    from app.knowledge_graph.neo4j_graph_store import Neo4jGraphStore
    if not isinstance(store, Neo4jGraphStore):
        return
    driver = store._get_driver()
    with driver.session() as s:
        s.run("MERGE (d:PolicyDocument {id:$id}) SET d.title=$t, d.domain=$dom",
              id=doc_id, t=meta.get("title", ""), dom=DOMAIN.value)
        for ent in data.get("entities", []):
            lbl = re.sub(r"[^a-zA-Z0-9]", "", ent.get("label", "Entity"))
            if not lbl:
                continue
            s.run(f"MERGE (n:{lbl} {{name:$n}})", n=ent["name"])
            s.run(f"MATCH (n:{lbl}{{name:$n}}),(d:PolicyDocument{{id:$id}}) MERGE (n)-[:MENTIONED_IN]->(d)",
                  n=ent["name"], id=doc_id)
        for rel in data.get("relationships", []):
            rt = re.sub(r"[^a-zA-Z0-9_]", "", rel.get("relation", "RELATED_TO").upper())
            if not rt:
                continue
            s.run(f"MATCH (a{{name:$s}}) MATCH (b{{name:$t}}) MERGE (a)-[:{rt}]->(b)",
                  s=rel.get("source"), t=rel.get("target"))


async def run_pipeline(include_pdfs: bool = True):
    print(f"Starting Government Ingestion Pipeline - root: {KNOWLEDGE_ROOT}")
    docs = total_chunks = 0

    for cat_dir in KNOWLEDGE_ROOT.rglob("*"):
        if cat_dir.name in SKIP_DIRS or cat_dir.is_file():
            continue

        for fpath in cat_dir.iterdir():
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in (".md", ".pdf", ".txt", ".html"):
                continue
            if fpath.suffix.lower() == ".pdf" and not include_pdfs:
                continue

            print(f"  Processing {fpath.relative_to(KNOWLEDGE_ROOT)}", flush=True)
            text = read_file(fpath)
            if not text or len(text.strip()) < 50:
                continue

            meta_path = KNOWLEDGE_ROOT / "metadata" / cat_dir.name / f"{fpath.stem}.json"
            if not meta_path.exists():
                meta_path = (KNOWLEDGE_ROOT / "metadata"
                             / cat_dir.parent.name / cat_dir.name / f"{fpath.stem}.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

            doc_id = str(uuid5(NAMESPACE_URL, f"{DOMAIN.value}:{fpath.name}"))
            chunks = semantic_chunking(text, chunk_size=350, overlap=80)

            try:
                await qdrant_service.upsert_chunks(DOMAIN, doc_id, chunks, meta)

                for chunk in chunks:
                    await extract_kg(chunk, meta, doc_id)

                print(f"  Indexed {fpath.name}  ->  {len(chunks)} chunks", flush=True)
                docs += 1
                total_chunks += len(chunks)
            except Exception as exc:
                print(f"  Skipped {fpath.name}  ->  {exc}", flush=True)
                continue

    print(f"\nPipeline complete!")
    print(f"  Domain   : {DOMAIN.value}")
    print(f"  Documents: {docs}")
    print(f"  Chunks   : {total_chunks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest government knowledge into vector and graph stores.")
    parser.add_argument("--text-only", action="store_true", help="Skip PDFs for a fast stable ingestion pass.")
    args = parser.parse_args()
    asyncio.run(run_pipeline(include_pdfs=not args.text_only))
