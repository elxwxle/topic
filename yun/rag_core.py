from __future__ import annotations

from pathlib import Path
from typing import List, Dict
import re


BASE_DIR = Path(__file__).resolve().parent
RAG_DIR = BASE_DIR / "rag_docs"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def load_rag_documents() -> List[Dict]:
    docs = []
    if not RAG_DIR.exists():
        return docs

    for path in RAG_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        docs.append({
            "source": path.name,
            "content": text,
        })
    return docs


def split_into_chunks(text: str, max_len: int = 180) -> List[str]:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    chunks = []
    buf = ""

    for line in lines:
        if len(buf) + len(line) + 1 <= max_len:
            buf += ("\n" if buf else "") + line
        else:
            if buf:
                chunks.append(buf)
            buf = line

    if buf:
        chunks.append(buf)

    return chunks


def build_rag_chunks() -> List[Dict]:
    docs = load_rag_documents()
    chunks = []

    for doc in docs:
        for chunk in split_into_chunks(doc["content"]):
            chunks.append({
                "source": doc["source"],
                "chunk": chunk,
            })

    return chunks


def keyword_score(query: str, text: str) -> int:
    q = normalize_text(query)
    t = normalize_text(text)

    score = 0
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", q):
        if token and token in t:
            score += len(token)
    return score


def rag_search(query: str, top_k: int = 3) -> List[Dict]:
    chunks = build_rag_chunks()
    scored = []

    for item in chunks:
        score = keyword_score(query, item["chunk"])
        if score > 0:
            scored.append({
                "source": item["source"],
                "chunk": item["chunk"],
                "score": score,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def rag_answer(query: str) -> str:
    results = rag_search(query, top_k=3)

    if not results:
        return "目前找不到可補充的說明資料。"

    lines = ["我找到一些可能相關的補充資訊："]
    for r in results:
        lines.append(f"【{r['source']}】{r['chunk']}")

    return "\n".join(lines)