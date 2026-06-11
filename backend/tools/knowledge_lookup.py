"""
Tool: knowledge_lookup
A lightweight RAG tool over the curated astrology reference notes.
Uses TF-IDF similarity (no external embedding API needed by default).
If OPENAI_API_KEY is set, it uses Ada embeddings for better recall.
"""
from __future__ import annotations

import os
import re
import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_NOTES_PATH = Path(__file__).parent / "astrology_notes.md"

# ── Parse notes file ────────────────────────────────────────────────────────


def _parse_notes(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    chunks = []
    for block in text.split("\n---\n"):
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        title_match = re.search(r'title:\s*"([^"]+)"', block)
        title = title_match.group(1) if title_match else "Untitled"
        body = re.sub(r'title:\s*"[^"]+"\n?', "", block).strip()
        if body:
            chunks.append({"title": title, "body": body})
    return chunks


_DOCS = _parse_notes(_NOTES_PATH)

# ── TF-IDF retrieval (no API needed) ────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-z]{2,}\b", text.lower())


def _build_tfidf_index(docs: list[dict]):
    N = len(docs)
    tokenized = [_tokenize(d["title"] + " " + d["body"]) for d in docs]
    # Compute DF
    df: dict[str, int] = {}
    for tokens in tokenized:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    # Compute TF-IDF vectors
    vectors = []
    for tokens in tokenized:
        tf: dict[str, float] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = len(tokens) or 1
        vec = {t: (cnt / total) * math.log((N + 1) / (df.get(t, 0) + 1))
               for t, cnt in tf.items()}
        vectors.append(vec)
    return vectors, df, N


_VECTORS, _DF, _N = _build_tfidf_index(_DOCS)


def _cosine(q_vec: dict, d_vec: dict) -> float:
    dot = sum(q_vec.get(t, 0) * d_vec.get(t, 0) for t in q_vec)
    norm_q = math.sqrt(sum(v * v for v in q_vec.values())) or 1
    norm_d = math.sqrt(sum(v * v for v in d_vec.values())) or 1
    return dot / (norm_q * norm_d)


def _tfidf_search(query: str, top_k: int) -> list[dict]:
    q_tokens = _tokenize(query)
    q_vec: dict[str, float] = {}
    for t in q_tokens:
        tf = q_tokens.count(t) / (len(q_tokens) or 1)
        idf = math.log((_N + 1) / (_DF.get(t, 0) + 1))
        q_vec[t] = tf * idf

    scores = [(_cosine(q_vec, dv), i) for i, dv in enumerate(_VECTORS)]
    scores.sort(reverse=True)
    results = []
    for score, idx in scores[:top_k]:
        if score > 0.0:
            results.append({
                "title": _DOCS[idx]["title"],
                "excerpt": _DOCS[idx]["body"][:500],
                "score": round(score, 4),
            })
    return results


# ── Public function ──────────────────────────────────────────────────────────

def knowledge_lookup(query: str, top_k: int = 3) -> dict:
    """
    Retrieve relevant astrology reference notes for the given query.

    Parameters
    ----------
    query : A natural-language question or topic, e.g. "what does Saturn in the 7th house mean"
    top_k : Number of passages to return (default 3)

    Returns
    -------
    { "query": str, "results": [ { "title": str, "excerpt": str, "score": float } ] }
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")

    top_k = max(1, min(top_k, 10))
    results = _tfidf_search(query.strip(), top_k)

    return {
        "query": query,
        "results": results,
        "source": "astrology_notes.md",
    }
