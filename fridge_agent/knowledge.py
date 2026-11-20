"""F3022 RAG 검색 Tool: 식품·영양·운동·생활 안내 문서(assets/guides.json)를 Chroma 에 색인하고 근거를 찾는다.

- 색인: FRIDGE_DATA_DIR/rag_chroma 의 'hankki_guides' 컬렉션. 문서가 바뀌면(내용 해시) 다시 만든다.
- 임베딩: 기본은 한국어 글자 조각(1~3글자) 해시 벡터라 키·인터넷 없이 같은 결과를 낸다.
  RAG_EMBED=model 이고 모델 키가 있으면 모델 임베딩(text-embedding-3-small)을 쓴다.
- 결과: 근거 문단·제목·출처·링크·거리. 거리가 멀면 NO_RESULT, 색인을 만들 수 없으면 NO_INDEX.
- 근거 검증: 응답 문장은 찾은 문단에서만 만들고, 문단 출처를 함께 보여 준다.
"""

import hashlib
import json
import math
import os
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parent / "assets" / "guides.json"
COLLECTION = "hankki_guides"
DIM = 1024
MAX_DISTANCE = 0.85  # 코사인 거리. 이보다 멀면 관련 문서가 없다고 본다.


SYNONYMS = {"짠": "나트륨 소금", "물": "수분", "잠": "수면", "자야": "수면 잠", "살": "체중 다이어트", "계란": "달걀", "소금": "나트륨", "설탕": "당류", "커피": "카페인", "술": "음주"}


def expand(question):
    """구어 표현을 문서 용어로 넓힌다: '물 얼마나' → '물 수분 얼마나'"""
    extra = [v for k, v in SYNONYMS.items() if k in question]
    return question + (" " + " ".join(extra) if extra else "")


def docs():
    return json.loads(DOCS.read_text(encoding="utf-8"))


def local_embed(text):
    """글자 조각 해시 임베딩(L2 정규화). 조사·어미가 붙어도 겹치는 조각으로 비슷한 문서를 찾는다."""
    vec = [0.0] * DIM
    for word in re.findall(r"[가-힣]+|[a-zA-Z]+|\d+", text.lower()):
        grams = {word} | {word[i : i + n] for n in (1, 2, 3) for i in range(len(word) - n + 1)}
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            vec[h % DIM] += (1.0 if len(g) == 1 else 2.0 if len(g) == 2 else 3.0) * (1 if (h >> 12) & 1 else -1)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(texts):
    if os.getenv("RAG_EMBED") == "model":
        import gateway

        if gateway.configured():
            key, url = gateway.openai_config()
            res = gateway.request_json(url + "/embeddings", {"model": os.getenv("RAG_EMBED_MODEL", "text-embedding-3-small"), "input": texts}, {"Authorization": "Bearer " + key}, timeout=20)
            return [x["embedding"] for x in res["data"]]
    return [local_embed(t) for t in texts]


def signature(items):
    mode = "model" if os.getenv("RAG_EMBED") == "model" else "local"
    return hashlib.sha256((mode + json.dumps(items, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:16]


def collection():
    """색인을 열고, 문서가 바뀌었으면 다시 만든다."""
    import chromadb

    path = Path(os.getenv("FRIDGE_DATA_DIR", ".")) / "rag_chroma"
    client = chromadb.PersistentClient(path=str(path))
    items = docs()
    sig = signature(items)
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    if (col.metadata or {}).get("signature") != sig or col.count() != len(items):
        client.delete_collection(COLLECTION)
        col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine", "signature": sig})
        col.add(
            ids=[x["id"] for x in items],
            documents=[x["title"] + "\n" + x["text"] for x in items],
            embeddings=embed([" ".join([x["title"], x["title"], x.get("keywords", ""), x.get("keywords", ""), x["text"]]) for x in items]),
            metadatas=[{"title": x["title"], "topic": x["topic"], "source": x["source"], "url": x["url"]} for x in items],
        )
    return col


def search(question, k=3):
    question = (question or "").strip()
    if not 2 <= len(question) <= 300:
        return {"ok": False, "error": "INVALID_INPUT"}
    try:
        col = collection()
        res = col.query(query_embeddings=embed([expand(question)]), n_results=k)
    except ImportError:
        return {"ok": False, "error": "RAG_DEPENDENCY_MISSING"}
    except Exception:  # 색인 경로·형식 문제
        return {"ok": False, "error": "NO_INDEX"}
    rows = [
        {"id": i, "title": m["title"], "excerpt": d.split("\n", 1)[-1], "source": m["source"], "url": m["url"], "topic": m["topic"], "distance": round(dist, 3)}
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        if dist <= MAX_DISTANCE
    ]
    if not rows:
        return {"ok": False, "error": "NO_RESULT"}
    rows = [r for r in rows if r["distance"] <= rows[0]["distance"] + 0.1]  # 1위보다 많이 먼 문서는 근거에서 뺀다
    return {"ok": True, "data": rows, "source": f"한끼 안내 문서 {col.count()}편 · Chroma({COLLECTION})"}



def heritage_search(question, limit=3):
    """2회차 국가유산 Chroma의 원본 컬렉션을 읽고 출처를 같은 응답 계약으로 반환한다."""
    path = os.getenv("HERITAGE_CHROMA_DIR")
    if not path or not (Path(path) / "chroma.sqlite3").is_file():
        return {"ok": False, "error": "NO_INDEX"}

    import gateway

    try:
        import chromadb

        client = chromadb.PersistentClient(path=path)
        collection = client.get_collection("heritage_docs")
        count = collection.count()
        if not count:
            return {"ok": False, "error": "NO_INDEX"}
        key, url = gateway.openai_config()
        if not key:
            return {"ok": False, "error": "MISSING_KEY"}
        response = gateway.request_json(
            url + "/embeddings",
            {"model": "text-embedding-3-small", "input": [question]},
            {"Authorization": "Bearer " + key}, timeout=20,
        )
        result = collection.query(query_embeddings=[response["data"][0]["embedding"]], n_results=min(count, limit))
        rows = []
        for chunk_id, body, meta, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0],
        ):
            if meta and body and meta.get("url"):
                rows.append({
                    "id": chunk_id, "title": meta.get("title") or chunk_id,
                    "excerpt": body[:1000], "source": meta.get("source_type") or "2회차 국가유산 문서",
                    "url": meta["url"], "distance": round(distance, 3),
                })
        if rows:
            return {"ok": True, "data": rows, "source": "2회차 국가유산 문서 · Chroma(heritage_docs)"}
        return {"ok": False, "error": "NO_RESULT"}
    except ImportError:
        return {"ok": False, "error": "RAG_DEPENDENCY_MISSING"}
    except chromadb.errors.NotFoundError:
        return {"ok": False, "error": "NO_INDEX"}
    except (ValueError, OSError, IndexError, KeyError, TypeError, RuntimeError):
        return {"ok": False, "error": "SOURCE_UNAVAILABLE"}
