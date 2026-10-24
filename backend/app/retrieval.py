"""Vector index over clause chunks: Chroma with local all-MiniLM-L6-v2 embeddings.

The embedding model runs on the local machine (ONNX, about 80 MB, downloaded by
Chroma on first use), so retrieval works without any API key, including in mock mode.

Each indexed document is a chunk's `search_text` (contract title + clause heading +
clause text); the metadata carries what a citation needs: contract, clause, page range.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import lru_cache

from . import config
from .ingestion.chunking import Chunk

log = logging.getLogger(__name__)

COLLECTION = "contract_clauses"


class IndexNotReady(RuntimeError):
    """Raised when the vector index has not been built yet."""


@dataclass
class ClauseHit:
    chunk_id: str
    contract_id: str
    contract_title: str
    counterparty: str
    clause_number: str | None
    heading: str
    page_start: int
    page_end: int
    citation: str
    score: float  # cosine similarity, higher is better (roughly 0-1)
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def _embedding_function():
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()


@lru_cache(maxsize=1)
def _client():
    import chromadb
    from chromadb.config import Settings

    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR), settings=Settings(anonymized_telemetry=False))


def build_index(chunks: list[Chunk]) -> int:
    """(Re)create the collection from scratch. Returns the number of indexed chunks."""
    client = _client()
    try:
        client.delete_collection(COLLECTION)
    except Exception:  # collection did not exist yet
        pass
    collection = client.create_collection(
        COLLECTION,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=_embedding_function(),
    )
    collection.add(
        ids=[c.chunk_id for c in chunks],
        documents=[c.search_text for c in chunks],
        metadatas=[
            {
                "contract_id": c.contract_id,
                "contract_title": c.contract_title,
                "counterparty": c.counterparty,
                "clause_number": c.clause_number or "",  # Chroma metadata cannot hold None
                "heading": c.heading,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "citation": c.citation,
                "text": c.text,
            }
            for c in chunks
        ],
    )
    return collection.count()


def _collection():
    # Looked up on every search so a rebuilt index is picked up without restarting.
    try:
        return _client().get_collection(COLLECTION, embedding_function=_embedding_function())
    except Exception as exc:
        raise IndexNotReady(
            "The clause index has not been built. Run `python -m scripts.ingest` in the backend folder."
        ) from exc


def warm_up() -> None:
    """Load the embedding model now, so the first real search is not slow."""
    _embedding_function()(["warm-up"])


def _hits(result: dict) -> list[ClauseHit]:
    hits = []
    for chunk_id, distance, meta in zip(result["ids"][0], result["distances"][0], result["metadatas"][0]):
        hits.append(
            ClauseHit(
                chunk_id=chunk_id,
                contract_id=meta["contract_id"],
                contract_title=meta["contract_title"],
                counterparty=meta["counterparty"],
                clause_number=meta["clause_number"] or None,
                heading=meta["heading"],
                page_start=int(meta["page_start"]),
                page_end=int(meta["page_end"]),
                citation=meta["citation"],
                score=round(1.0 - float(distance), 3),
                text=meta["text"],
            )
        )
    return hits


def contract_ids() -> list[str]:
    metas = _collection().get(include=["metadatas"])["metadatas"]
    return sorted({m["contract_id"] for m in metas})


@dataclass
class SearchOutcome:
    hits: list[ClauseHit]
    contracts_checked: list[str]
    contracts_without_match: list[str]  # checked, but nothing scored above the threshold
    weak_matches_only: bool             # True if no hit passed the threshold (closest ones returned)


def search(
    query: str,
    contract_id: str | None = None,
    top_k: int = 5,
    group_by_contract: bool = False,
    per_contract: int = 2,
    min_score: float | None = None,
) -> SearchOutcome:
    """Semantic clause search.

    With `group_by_contract`, every contract is searched separately and its best
    `per_contract` clauses are returned, so questions like "which contracts renew
    automatically?" cannot silently miss a contract.

    Hits below `min_score` are dropped. If that would leave nothing, the closest few
    are returned with `weak_matches_only=True`, so the caller can tell "the contracts
    don't cover this" apart from "the question was phrased differently".
    """
    threshold = config.RETRIEVAL_MIN_SCORE if min_score is None else min_score
    collection = _collection()

    if group_by_contract and not contract_id:
        checked = contract_ids()
        hits: list[ClauseHit] = []
        for cid in checked:
            result = collection.query(query_texts=[query], n_results=per_contract, where={"contract_id": cid})
            hits.extend(_hits(result))
    else:
        checked = [contract_id] if contract_id else contract_ids()
        where = {"contract_id": contract_id} if contract_id else None
        result = collection.query(query_texts=[query], n_results=top_k, where=where)
        hits = sorted(_hits(result), key=lambda h: h.score, reverse=True)

    kept = [h for h in hits if h.score >= threshold]
    weak = not kept
    if weak:
        kept = sorted(hits, key=lambda h: h.score, reverse=True)[:3]
        log.info("no hit above min_score %.2f for %r; returning %d weak matches", threshold, query, len(kept))
    matched = {h.contract_id for h in kept if h.score >= threshold}
    return SearchOutcome(
        hits=kept,
        contracts_checked=checked,
        contracts_without_match=[c for c in checked if c not in matched],
        weak_matches_only=weak,
    )
