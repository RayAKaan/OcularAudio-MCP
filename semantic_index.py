"""Local-first semantic and hybrid retrieval for OcularAudio.

Phase 4 adds a deterministic TF-IDF vector space over timestamped evidence.
It provides semantic similarity without requiring an external API, model download,
or vector database. The same index can combine transcript and OCR evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)
STOPWORDS = {
    "a","an","and","are","as","at","be","by","for","from","how","i","in","is","it",
    "of","on","or","that","the","this","to","was","what","when","where","which","who",
    "why","with","you",
}


@dataclass(frozen=True)
class SemanticDocument:
    document_id: str
    text: str
    source: str = "transcript"
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    chapter: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SemanticMatch:
    document_id: str
    score: float
    semantic_score: float
    lexical_score: float
    text: str
    source: str
    start_seconds: float
    end_seconds: float
    chapter: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if token.lower() not in STOPWORDS
    ]


def _term_frequency(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0.0) + 1.0
    total = max(1.0, float(len(tokens)))
    return {key: value / total for key, value in counts.items()}


class TfidfIndex:
    """Small persistent-friendly TF-IDF index suitable for local media evidence."""

    def __init__(self, documents: Iterable[SemanticDocument] = ()):
        self.documents = list(documents)
        self._idf: dict[str, float] = {}
        self._vectors: list[dict[str, float]] = []
        self._build()

    def _build(self) -> None:
        token_lists = [tokenize(doc.text) for doc in self.documents]
        document_frequency: dict[str, int] = {}
        for tokens in token_lists:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1
        count = max(1, len(self.documents))
        self._idf = {
            token: math.log((1 + count) / (1 + frequency)) + 1.0
            for token, frequency in document_frequency.items()
        }
        self._vectors = []
        for tokens in token_lists:
            tf = _term_frequency(tokens)
            vector = {token: value * self._idf.get(token, 1.0) for token, value in tf.items()}
            norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
            self._vectors.append({token: value / norm for token, value in vector.items()})

    def semantic_scores(self, query: str) -> list[float]:
        tokens = tokenize(query)
        tf = _term_frequency(tokens)
        vector = {token: value * self._idf.get(token, 1.0) for token, value in tf.items()}
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vector = {token: value / norm for token, value in vector.items()}
        return [
            round(sum(vector.get(token, 0.0) * doc_vector.get(token, 0.0) for token in vector), 6)
            for doc_vector in self._vectors
        ]


def lexical_scores(documents: Iterable[SemanticDocument], query: str) -> list[float]:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return [0.0 for _ in documents]
    scores = []
    for document in documents:
        tokens = set(tokenize(document.text))
        overlap = len(query_tokens & tokens)
        coverage = overlap / len(query_tokens)
        phrase = query.lower().strip() in document.text.lower()
        scores.append(round(min(1.0, coverage * 0.8 + (0.2 if phrase else 0.0)), 6))
    return scores


def hybrid_search(
    documents: list[SemanticDocument],
    query: str,
    top_k: int = 8,
    semantic_weight: float = 0.65,
) -> list[SemanticMatch]:
    if not query.strip() or not documents:
        return []
    weight = max(0.0, min(1.0, float(semantic_weight)))
    index = TfidfIndex(documents)
    semantic = index.semantic_scores(query)
    lexical = lexical_scores(documents, query)
    matches = []
    for doc, sem, lex in zip(documents, semantic, lexical):
        score = round(weight * sem + (1.0 - weight) * lex, 6)
        matches.append(SemanticMatch(
            document_id=doc.document_id,
            score=score,
            semantic_score=sem,
            lexical_score=lex,
            text=doc.text,
            source=doc.source,
            start_seconds=doc.start_seconds,
            end_seconds=doc.end_seconds,
            chapter=doc.chapter,
            metadata=doc.metadata,
        ))
    matches.sort(key=lambda item: (-item.score, item.start_seconds, item.document_id))
    return matches[:max(1, min(int(top_k), 50))]


def fuse_evidence(
    transcript_documents: Iterable[SemanticDocument],
    visual_documents: Iterable[SemanticDocument],
    query: str,
    top_k: int = 8,
    semantic_weight: float = 0.65,
) -> list[SemanticMatch]:
    """Search transcript and OCR evidence together with source-aware tie-breaking."""
    docs = list(transcript_documents) + list(visual_documents)
    return hybrid_search(docs, query, top_k=top_k, semantic_weight=semantic_weight)
