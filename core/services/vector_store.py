import os
import re
from pathlib import Path
import chromadb

CHROMA_PATH = os.getenv("SENTINEL_CHROMA_PATH", ".chroma")
COLLECTION = "runbooks"
CONTENT_CAP = 1500  # chars of Symptoms + Root Causes sent to the ranking prompt per runbook


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


def find_matching_runbooks(error_signature: str, top_k: int = 3, include_content: bool = False) -> list[dict]:
    col = _col()
    count = col.count()
    if count == 0:
        return []

    results = col.query(query_texts=[error_signature], n_results=min(top_k, count))
    out = []
    for doc_id, meta, doc, dist in zip(
        results["ids"][0],
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        match = {
            "id": doc_id,
            "title": meta["title"],
            "similarity_score": round(1 - dist, 3),
            "primary_action": _first_action(doc),
        }
        if include_content:  # prompt-only; callers must not persist it
            match["content"] = _prompt_content(doc)
        out.append(match)
    return out


def _section(doc: str, heading: str) -> str:
    m = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", doc, flags=re.M | re.S)
    return m.group(1).strip() if m else ""


def _prompt_content(doc: str) -> str:
    text = f"Symptoms:\n{_section(doc, 'Symptoms')}\n\nRoot causes:\n{_section(doc, 'Root Causes')}"
    return text[:CONTENT_CAP]


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
