from pathlib import Path
import chromadb

CHROMA_PATH = ".chroma"
COLLECTION = "runbooks"

def _col():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

def ingest_runbooks(runbooks_dir: str) -> int:
    col = _col()
    docs, ids, metas = [], [], []
    for path in Path(runbooks_dir).glob("*.md"):
        docs.append(path.read_text())
        ids.append(path.stem)
        metas.append({"title": path.stem.replace("_", " ").title()})
    if docs:
        col.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(docs)

def find_matching_runbooks(error_signature: str, top_k: int = 3) -> list[dict]:
    col = _col()
    count = col.count()
    if count == 0:
        return []

    results = col.query(query_texts=[error_signature], n_results=min(top_k, count))
    out = []
    for doc_id, meta, doc, dist in zip(
        results["ids"][0], results["metadatas"][0],
        results["documents"][0], results["distances"][0],
    ):
        out.append({
            "id": doc_id,
            "title": meta["title"],
            "similarity_score": round(1 - dist, 3),
            "primary_action": _first_action(doc),
        })
    return out

def _first_action(doc: str) -> str:
    in_actions = False
    for line in doc.splitlines():
        if "Immediate Actions" in line:
            in_actions = True
            continue
        if in_actions and line.startswith("1."):
            return line[2:].strip()
        if in_actions and line.startswith("##"):
            break
    return "See runbook for details."
