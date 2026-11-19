"""Read the existing second-round Chroma collection using its original embedding space."""

import os
from pathlib import Path
import gateway


def search(term):
    root = os.getenv("HERITAGE_RAG_DIR")
    path = Path(root) / "data" / "chroma" if root else None
    if not path or not (path / "chroma.sqlite3").is_file():
        return {"ok": False, "error": "NO_INDEX", "message": "2회차 근거 문서 색인이 아직 없습니다."}
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(path))
        if "heritage_docs" not in [getattr(c, "name", c) for c in client.list_collections()]:
            return {"ok": False, "error": "NO_INDEX"}
        collection = client.get_collection("heritage_docs")
        if not collection.count():
            return {"ok": False, "error": "NO_INDEX"}
        if not gateway.configured():
            return {"ok": False, "error": "MISSING_KEY", "setting": "GMS_KEY"}
        result = collection.query(
            query_embeddings=[gateway.embed(term)],
            n_results=min(3, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        data = [
            {
                "id": i,
                "title": m.get("title") or m.get("item_id") or i,
                "excerpt": t[:500],
                "url": m.get("url") or m.get("source_url"),
                "distance": round(d, 4),
            }
            for i, t, m, d in zip(
                result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
            )
        ]
        return (
            {"ok": True, "data": data, "source": "2회차 heritage_docs"}
            if data
            else {"ok": False, "error": "NO_RESULT"}
        )
    except ImportError:
        return {"ok": False, "error": "RAG_DEPENDENCY_MISSING"}
    except Exception:
        return {"ok": False, "error": "SOURCE_UNAVAILABLE"}
