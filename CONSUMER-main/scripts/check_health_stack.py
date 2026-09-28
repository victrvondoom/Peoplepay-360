import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings
from app.rag.retrieval.factory import get_vector_store
from app.knowledge_graph.factory import get_graph_store


def main() -> None:
    settings = get_settings()
    result = {
        "vector_store": get_vector_store().health_check(),
        "graph_store": get_graph_store().health_check(),
        "supabase": {
            "status": "configured" if settings.supabase_url and settings.supabase_service_role_key else "missing_keys",
            "url": settings.supabase_url or "",
        },
        "gemini": {
            "status": "disabled" if settings.disable_external_llm else ("configured" if settings.gemini_api_key else "missing_key"),
        },
        "backends": {
            "vector_store_backend": settings.vector_store_backend,
            "graph_store_backend": settings.graph_store_backend,
        },
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
