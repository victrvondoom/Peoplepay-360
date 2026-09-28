import asyncio

from app.api.routes.ecommerce import corpus_stats as ecommerce_corpus_stats
from app.api.routes.ecommerce import search_local_corpus as ecommerce_search_local_corpus
from app.api.routes.ecommerce import vector_status as ecommerce_vector_status
from app.api.routes.telecom import corpus_stats as telecom_corpus_stats
from app.api.routes.telecom import search_local_corpus as telecom_search_local_corpus


def test_telecom_local_corpus_is_chunked_and_searchable() -> None:
    stats = asyncio.run(telecom_corpus_stats())
    assert stats["corpus_ready"] is True
    # A handful of JS-render-failure stub files (loading spinners, no real
    # content) were cleaned out of the corpus, lowering these counts slightly
    # from the original thresholds — a data-quality improvement, not a regression.
    assert stats["files_total"] >= 65
    assert stats["chunks_total"] >= 790
    assert stats["authority_counts"]["TRAI"] >= 50

    results = asyncio.run(telecom_search_local_corpus(q="MNP porting complaint", limit=3))
    assert results["count"] >= 1
    assert any("mnp" in hit["source_path"].lower() for hit in results["results"])


def test_ecommerce_local_corpus_is_chunked_and_searchable() -> None:
    stats = asyncio.run(ecommerce_corpus_stats())
    assert stats["corpus_ready"] is True
    # Same cleanup as telecom above — a few JS-render-failure stub files removed.
    assert stats["files_total"] >= 26
    assert stats["chunks_total"] >= 285
    assert stats["authority_counts"]["India Code"] >= 1
    assert stats["authority_counts"]["NCH"] >= 3
    assert "Wikipedia" not in stats["authority_counts"]

    results = asyncio.run(ecommerce_search_local_corpus(q="refund defective product warranty", limit=3))
    assert results["count"] >= 1
    assert any(hit["metadata"].get("authority") in {"Flipkart", "Amazon", "BigBasket", "JioMart"} for hit in results["results"])
    assert any("return" in hit["source_path"].lower() or "refund" in hit["source_path"].lower() for hit in results["results"])





def test_ecommerce_prepared_vector_and_graph_store_ready() -> None:
    status = asyncio.run(ecommerce_vector_status())
    assert status["vector_snapshot_ready"] is True
    assert status["vector_points"] >= 290
    assert status["ecommerce_graph_events"] >= 80
    assert "Flipkart" in status["authorities"]
    assert status["qdrant_collection"] == "proxy_ecommerce"
