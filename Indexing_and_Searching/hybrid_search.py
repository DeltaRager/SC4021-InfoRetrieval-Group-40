"""
Hybrid BM25 + Vector retrieval with RRF fusion and cross-encoder reranking.

Architecture:
  EmbeddingClient  – thin HTTP adapter for the embedding service (:8081)
  RerankerClient   – thin HTTP adapter for the reranker service  (:8082)
  HybridSearchService – orchestrates lexical + vector → RRF → rerank pipeline

Vector retrieval uses a dual-path composition formula:
  query_combined_vector = normalize(main_weight * f(a+b) + concept_weight * f(b))
where:
  f(a+b) = embedding of the full query text (main channel)
  f(b)   = embedding of extracted concepts only (concept channel)
  main_weight    = VECTOR_MAIN_WEIGHT    (default 1.0, env-configurable)
  concept_weight = VECTOR_CONCEPT_WEIGHT (default 0.2, env-configurable)

Document chunks are indexed with the analogous weighted formula:
  chunk_vector = normalize(main_weight * chunk_main_vector + concept_weight * chunk_concept_vector)

This makes concept-heavy queries and documents mutually reinforcing without
requiring a separate kNN field or online reweighting at query time.
The concept weight < 1.0 ensures that generic concepts (e.g., "AI") do not
dominate over the full-text embedding for semantically weak matches.

Vector retrieval operates on chunk records (one Solr doc per chunk).
Chunk hits are collapsed to source documents by `doc_id` before RRF fusion.
Lexical retrieval and all result rendering remain document-oriented.

Config (env vars with defaults):
  EMBEDDING_URL        http://localhost:8081
  RERANKER_URL         http://localhost:8082
  HYBRID_LEXICAL_K     100
  HYBRID_VECTOR_K      200   (larger than lexical_k to compensate for multi-chunk docs)
  HYBRID_RRF_K         60
  HYBRID_RERANK_K      100   (number of fused docs whose chunks are expanded for reranking)
  HYBRID_RERANK_CHUNK_K 300  (max total chunks sent to reranker; caps expansion)
  HYBRID_RERANK_TOP_K  50    (top-N docs kept from reranker output for display)
  SEARCH_ROWS          20    (used only in degraded/lexical-only path)
  EMBED_BATCH_SIZE     32
  EMBEDDING_DIM        1024
  VECTOR_MAIN_WEIGHT   1.0   (weight for main/full-text embedding in combined vector)
  VECTOR_CONCEPT_WEIGHT 0.2  (weight for concept embedding; lower = less concept dominance)
"""

from __future__ import annotations

import logging
import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from query_intent import infer_intent, QueryIntentProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EMBEDDING_URL    = os.getenv("EMBEDDING_URL",    "http://localhost:8081")
RERANKER_URL     = os.getenv("RERANKER_URL",     "http://localhost:8082")
HYBRID_LEXICAL_K      = int(os.getenv("HYBRID_LEXICAL_K",      "100"))
HYBRID_VECTOR_K       = int(os.getenv("HYBRID_VECTOR_K",       "200"))
HYBRID_RRF_K          = int(os.getenv("HYBRID_RRF_K",          "60"))
HYBRID_RERANK_K       = int(os.getenv("HYBRID_RERANK_K",       "100"))
HYBRID_RERANK_CHUNK_K = int(os.getenv("HYBRID_RERANK_CHUNK_K", "300"))
HYBRID_RERANK_TOP_K   = int(os.getenv("HYBRID_RERANK_TOP_K",   "50"))
SEARCH_ROWS           = int(os.getenv("SEARCH_ROWS",            "20"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE",  "32"))
EMBEDDING_DIM    = int(os.getenv("EMBEDDING_DIM",     "1024"))

# ---------------------------------------------------------------------------
# Dual-path vector combination weights (env-var overridable)
# ---------------------------------------------------------------------------

VECTOR_MAIN_WEIGHT    = float(os.getenv("VECTOR_MAIN_WEIGHT",    "1.0"))
VECTOR_CONCEPT_WEIGHT = float(os.getenv("VECTOR_CONCEPT_WEIGHT", "0.2"))

# ---------------------------------------------------------------------------
# Query intent weight config (env-var overridable, alpha + beta must = 1.0)
# ---------------------------------------------------------------------------

_INTENT_KEYWORD_ALPHA  = float(os.getenv("QUERY_INTENT_KEYWORD_ALPHA",  "0.8"))
_INTENT_KEYWORD_BETA   = float(os.getenv("QUERY_INTENT_KEYWORD_BETA",   "0.2"))
_INTENT_MIXED_ALPHA    = float(os.getenv("QUERY_INTENT_MIXED_ALPHA",    "0.5"))
_INTENT_MIXED_BETA     = float(os.getenv("QUERY_INTENT_MIXED_BETA",     "0.5"))
_INTENT_SEMANTIC_ALPHA = float(os.getenv("QUERY_INTENT_SEMANTIC_ALPHA", "0.3"))
_INTENT_SEMANTIC_BETA  = float(os.getenv("QUERY_INTENT_SEMANTIC_BETA",  "0.7"))


def _validate_intent_weights() -> None:
    pairs = [
        ("keyword",  _INTENT_KEYWORD_ALPHA,  _INTENT_KEYWORD_BETA),
        ("mixed",    _INTENT_MIXED_ALPHA,    _INTENT_MIXED_BETA),
        ("semantic", _INTENT_SEMANTIC_ALPHA, _INTENT_SEMANTIC_BETA),
    ]
    for label, alpha, beta in pairs:
        if abs(alpha + beta - 1.0) > 1e-6:
            logger.warning(
                "Intent weights for '%s' do not sum to 1.0 (alpha=%.3f beta=%.3f); "
                "falling back to defaults.",
                label, alpha, beta,
            )


_validate_intent_weights()


# ---------------------------------------------------------------------------
# Vector utilities
# ---------------------------------------------------------------------------

def _combine_vectors(
    main_vec: list[float],
    concept_vec: list[float],
    main_weight: float = VECTOR_MAIN_WEIGHT,
    concept_weight: float = VECTOR_CONCEPT_WEIGHT,
) -> list[float]:
    """Weighted elementwise combination of two vectors, L2-normalised.

    Implements the dual-path combination formula:
        combined = normalize(main_weight * f(a+b) + concept_weight * f(b))

    The default weights (main=1.0, concept=0.2) keep the full-text embedding
    as the primary signal while giving the concept channel a secondary boost.
    Equal weights (1.0, 1.0) reproduce the previous equal-weight behaviour.

    If the concept vector is all zeros (no concepts present) the result is
    the normalised scaled main vector.  Returns the zero vector in the
    degenerate case where the weighted sum is the zero vector.
    """
    dim = len(main_vec)
    summed = [main_weight * main_vec[i] + concept_weight * concept_vec[i] for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in summed))
    if norm == 0.0:
        return summed
    return [v / norm for v in summed]


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """Intermediate result in the fusion/reranking pipeline."""
    id: str              # chunk-level Solr id (e.g. "abc123__c1")
    doc_id: str          # stable source-document id (e.g. "abc123")
    source: str          # "lexical" | "vector" | "both"
    raw_score: float
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    search_text: str = ""
    display_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalInfo:
    """Diagnostics passed to the template via `retrieval_info`."""
    mode: str = "hybrid"            # "hybrid" | "lexical"
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)
    lexical_hits: int = 0
    vector_hits: int = 0
    fused_hits: int = 0
    reranked_hits: int = 0
    latency_ms: dict[str, float] = field(default_factory=dict)
    # Query intent diagnostics
    intent_label: str = ""          # "keyword" | "semantic" | "mixed" | ""
    alpha: float = 0.5              # BM25 weight used in weighted RRF
    beta: float = 0.5               # vector weight used in weighted RRF
    intent_signals: dict[str, float] = field(default_factory=dict)
    # Full fused doc_id list (all candidates before top-N slicing).
    # Used by analytics so charts cover the whole matched set, not just the
    # lexical BM25 slice.  Not included in as_dict() — template doesn't need it.
    fused_doc_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "degraded": self.degraded,
            "warnings": self.warnings,
            "lexical_hits": self.lexical_hits,
            "vector_hits": self.vector_hits,
            "fused_hits": self.fused_hits,
            "reranked_hits": self.reranked_hits,
            "latency_ms": self.latency_ms,
            "intent_label": self.intent_label,
            "alpha": self.alpha,
            "beta": self.beta,
            "intent_signals": self.intent_signals,
        }


# ---------------------------------------------------------------------------
# Embedding client
# ---------------------------------------------------------------------------

class EmbeddingClient:
    """HTTP adapter for the embedding service.

    Expected wire format (probed against :8081):
      POST /embed
      Body: {"texts": ["...", ...]}
      Response: {"embeddings": [[float, ...], ...]}

    Falls back gracefully: returns None on any error.
    """

    def __init__(self, base_url: str = EMBEDDING_URL, timeout: int = 10):
        normalized = base_url.rstrip("/")
        if normalized.endswith("/embed") or normalized.endswith("/v1/embeddings"):
            self._urls = [normalized]
        else:
            self._urls = [normalized + "/embed", normalized + "/v1/embeddings"]
        self._timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Return a list of embedding vectors, one per text, or None on failure."""
        if not texts:
            return []
        last_error: Exception | None = None
        for url in self._urls:
            payload = {"texts": texts} if url.endswith("/embed") else {"input": texts}
            try:
                resp = requests.post(url, json=payload, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings") or data.get("vectors") or data.get("data")
                if embeddings is None:
                    logger.warning(
                        "Embedding service response missing embeddings payload at %s: %s",
                        url,
                        list(data.keys()),
                    )
                    return None
                if embeddings and isinstance(embeddings[0], dict):
                    parsed = [item.get("embedding") for item in embeddings]
                    if any(embedding is None for embedding in parsed):
                        logger.warning("Embedding service returned malformed embedding rows at %s.", url)
                        return None
                    return parsed
                return embeddings
            except requests.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None
                if status == 404 and url != self._urls[-1]:
                    continue
                logger.warning("Embedding service request failed at %s: %s", url, exc)
                return None
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Embedding service unreachable at %s: %s", url, exc)
                return None
            except Exception as exc:
                last_error = exc
                logger.warning("Embedding client error at %s: %s", url, exc)
                return None

        if last_error is not None:
            logger.warning("Embedding service failed for all configured endpoints: %s", last_error)
        return None

    def embed_query(self, text: str) -> list[float] | None:
        """Embed a single query string."""
        result = self.embed([text])
        if result is None or not result:
            return None
        return result[0]

    def embed_batch(self, texts: list[str], batch_size: int = EMBED_BATCH_SIZE) -> list[list[float] | None]:
        """Embed texts in batches; individual None entries on partial failure."""
        results: list[list[float] | None] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_result = self.embed(batch)
            if batch_result is None:
                if len(batch) == 1:
                    results.append(None)
                    continue
                for text in batch:
                    single_result = self.embed([text])
                    results.append(single_result[0] if single_result else None)
            else:
                results.extend(batch_result)
        return results


# ---------------------------------------------------------------------------
# Reranker client
# ---------------------------------------------------------------------------

class RerankerClient:
    """HTTP adapter for the cross-encoder reranker service.

    Expected wire format (probed against :8082):
      POST /rerank
      Body: {"query": "...", "documents": ["...", ...]}
      Response: {"scores": [float, ...]}   (same order as documents)

    Falls back gracefully: returns None on any error.
    """

    def __init__(self, base_url: str = RERANKER_URL, timeout: int = 15):
        # llama-server exposes /v1/reranking; fall back to /rerank for other services
        base = base_url.rstrip("/")
        self._url = base + "/v1/reranking"
        self._fallback_url = base + "/rerank"
        self._timeout = timeout

    def rerank(
        self,
        query: str,
        candidates: list[Candidate],
        top_k: int = HYBRID_RERANK_K,
    ) -> list[Candidate] | None:
        """Return candidates sorted by rerank score, or None on failure."""
        if not candidates:
            return candidates
        # Truncate each document to avoid exceeding the reranker's context window.
        # llama-server bge-reranker-v2-m3 has n_ctx=8192; with 50 docs and query
        # overhead, cap each doc at 512 chars (~128 tokens) to stay well within budget.
        max_doc_chars = int(os.getenv("RERANKER_MAX_DOC_CHARS", "512"))
        documents = [c.search_text[:max_doc_chars] for c in candidates]
        try:
            resp = requests.post(
                self._url,
                json={"query": query, "documents": documents},
                timeout=self._timeout,
            )
            if resp.status_code == 404:
                # Primary URL not found; try legacy /rerank path
                resp = requests.post(
                    self._fallback_url,
                    json={"query": query, "documents": documents},
                    timeout=self._timeout,
                )
            resp.raise_for_status()
            data = resp.json()
            scores = data.get("scores") or data.get("results")
            if scores is None:
                logger.warning("Reranker response missing 'scores' key: %s", list(data.keys()))
                return None
            # scores may be a list of floats or a list of dicts with index/score
            if scores and isinstance(scores[0], dict):
                # Handle formats like [{"index": 0, "score": 0.9}, ...]
                float_scores = [0.0] * len(candidates)
                for item in scores:
                    idx = item.get("index", item.get("corpus_id"))
                    sc  = item.get("score", item.get("relevance_score", 0.0))
                    if idx is not None and 0 <= idx < len(float_scores):
                        float_scores[idx] = float(sc)
                scores = float_scores

            for cand, sc in zip(candidates, scores):
                cand.rerank_score = float(sc)

            # Return all scored candidates sorted by score; caller is responsible
            # for any top-k slicing (e.g. max-pool to doc level then slice).
            return sorted(candidates, key=lambda c: c.rerank_score, reverse=True)
        except requests.RequestException as exc:
            logger.warning("Reranker service unreachable: %s", exc)
            return None
        except Exception as exc:
            logger.warning("Reranker client error: %s", exc)
            return None


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    lexical_ids: list[str],
    vector_ids: list[str],
    rrf_k: int = HYBRID_RRF_K,
    lexical_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> list[tuple[str, float]]:
    """Weighted RRF: score += weight * (1 / (rrf_k + rank)).

    When lexical_weight == vector_weight == 0.5 the result is identical to
    standard (equal-weight) RRF.  Pass intent-derived alpha/beta to skew
    fusion toward the stronger retriever for the given query.

    Returns [(id, score)] sorted descending by score.
    """
    scores: dict[str, float] = {}

    for rank, doc_id in enumerate(lexical_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + lexical_weight / (rrf_k + rank)

    for rank, doc_id in enumerate(vector_ids, start=1):
        scores[doc_id] = scores.get(doc_id, 0.0) + vector_weight / (rrf_k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Hybrid search service
# ---------------------------------------------------------------------------

DISPLAY_FIELDS = (
    "id,doc_id,type,title,body,subreddit,score,created_date,"
    "source_dataset,polarity_label,polarity_confidence,"
    "subjectivity_label,subjectivity_confidence,"
    "model_mentions,vendor_mentions,search_text,chunk_text,concepts"
)

# Fields returned from chunk records during vector retrieval
# (chunk_text is used as the evidence snippet for the best-matching chunk)
CHUNK_VECTOR_FIELDS = DISPLAY_FIELDS + ",chunk_index"
FACET_FIELDS = (
    "type",
    "subreddit",
    "polarity_label",
    "subjectivity_label",
    "source_dataset",
    "model_mentions",
    "vendor_mentions",
)


def _facets_from_results(results: list[dict]) -> dict[str, list]:
    """Compute facet counts from the final result set.

    Single-value fields (type, subreddit, polarity_label, subjectivity_label, source_dataset)
    and multi-value fields (model_mentions, vendor_mentions) are both handled.
    Returns a dict of {field: [val, count, val, count, ...]} matching the
    flat-pairs format expected by the template's facet_links macro.
    """
    counts: dict[str, dict[str, int]] = {f: {} for f in FACET_FIELDS}
    for doc in results:
        for field in FACET_FIELDS:
            value = doc.get(field)
            if not value:
                continue
            # model_mentions / vendor_mentions are lists; others are strings
            values = value if isinstance(value, list) else [value]
            for v in values:
                v = str(v).strip()
                if v:
                    counts[field][v] = counts[field].get(v, 0) + 1

    facets: dict[str, list] = {}
    for field, bucket in counts.items():
        flat: list = []
        for val, count in sorted(bucket.items(), key=lambda x: -x[1]):
            flat.extend([val, count])
        facets[field] = flat
    return facets


def _sort_policy(sort: str) -> str:
    """Normalise the requested sort into one of two canonical policies.

    Returns:
        "recency"   – order final results by ``created_date desc``
        "relevance" – order final results by pipeline score desc (default)
    """
    if sort and "created_date" in sort:
        return "recency"
    return "relevance"


def _collapse_filter(sort: str = "score desc") -> str:
    escaped_sort = sort.replace("\\", "\\\\").replace('"', '\\"')
    return f'{{!collapse field=doc_id sort="{escaped_sort}"}}'


def _json_facet_payload() -> str:
    facets: dict[str, Any] = {"unique_docs": "unique(doc_id)"}
    for field in FACET_FIELDS:
        facets[field] = {
            "type": "terms",
            "field": field,
            "limit": -1,
            "mincount": 1,
            "facet": {"docs": "unique(doc_id)"},
        }
    return json.dumps(facets, separators=(",", ":"))


def _parse_doc_facets(payload: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
    json_facets = payload.get("facets")
    if isinstance(json_facets, dict):
        parsed: dict[str, Any] = {}
        unique_docs = json_facets.get("unique_docs")
        for field in FACET_FIELDS:
            facet_info = json_facets.get(field, {})
            buckets = facet_info.get("buckets", []) if isinstance(facet_info, dict) else []
            flat_pairs: list[Any] = []
            for bucket in buckets:
                val = bucket.get("val")
                count = bucket.get("docs", bucket.get("count", 0))
                if val is None:
                    continue
                flat_pairs.extend([val, int(count)])
            parsed[field] = flat_pairs
        return parsed, int(unique_docs) if isinstance(unique_docs, (int, float)) else None

    classic_facets = payload.get("facet_counts", {}).get("facet_fields", {})
    return classic_facets, None


class HybridSearchService:
    """Orchestrates lexical → vector → RRF → rerank pipeline.

    Args:
        solr_url:   Full Solr select URL (e.g. http://localhost:8983/solr/reddit_ai/select)
        embedder:   EmbeddingClient instance
        reranker:   RerankerClient instance
    """

    def __init__(
        self,
        solr_url: str,
        embedder: EmbeddingClient,
        reranker: RerankerClient,
    ):
        self._solr_url = solr_url
        self._embedder = embedder
        self._reranker = reranker

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def search(
        self,
        solr_q: str,
        fq: list[str],
        qf: str,
        pf: str,
        bq: list[str],
        sort: str,
        use_nlp: bool,
        query_text: str,
        use_vector: bool = True,
        concept_text: str = "",
    ) -> tuple[list[dict], dict, int, RetrievalInfo]:
        """Run the full hybrid pipeline.

        Args:
            concept_text: Concepts-only text for the dual-path query vector
                          (embedding channel b = f(b)).  Derived by joining
                          extracted concept phrases with spaces.  When empty,
                          the combined query vector reduces to the normalised
                          main embedding.

        Returns:
            (results, facets, num_found, retrieval_info)
        """
        info = RetrievalInfo()
        t_total = time.perf_counter()

        # Stage 1: lexical retrieval
        t0 = time.perf_counter()
        lexical_docs, facets, num_found = self._lexical_retrieval(
            solr_q, fq, qf, pf, bq, sort, use_nlp
        )
        info.latency_ms["lexical"] = round((time.perf_counter() - t0) * 1000, 1)
        info.lexical_hits = len(lexical_docs)

        if not lexical_docs:
            info.mode = "lexical"
            info.latency_ms["total"] = round((time.perf_counter() - t_total) * 1000, 1)
            return [], facets, num_found, info

        # Stage 2: vector retrieval (chunk-level kNN → collapsed to doc_id)
        if not use_vector:
            info.mode = "lexical"
            results = self._finalize_lexical(lexical_docs, solr_q, fq, qf, sort)
            # Populate fused_doc_ids from the lexical candidate set so analytics
            # covers the same population as the results.
            seen_lex_ids: set[str] = set()
            for d in lexical_docs:
                did = d.get("doc_id") or d.get("id")
                if did and did not in seen_lex_ids:
                    seen_lex_ids.add(did)
                    info.fused_doc_ids.append(did)
            info.latency_ms["total"] = round((time.perf_counter() - t_total) * 1000, 1)
            return results, facets, num_found, info

        t0 = time.perf_counter()
        vector_docs, best_chunk_texts = self._vector_retrieval(
            query_text, fq, concept_text=concept_text
        )
        info.latency_ms["vector"] = round((time.perf_counter() - t0) * 1000, 1)

        if vector_docs is None:
            # Vector stage failed → degrade to lexical-only
            info.degraded = True
            info.mode = "lexical"
            info.warnings.append("Vector retrieval unavailable; serving lexical results only.")
            results = self._finalize_lexical(lexical_docs, solr_q, fq, qf, sort)
            seen_lex_ids2: set[str] = set()
            for d in lexical_docs:
                did = d.get("doc_id") or d.get("id")
                if did and did not in seen_lex_ids2:
                    seen_lex_ids2.add(did)
                    info.fused_doc_ids.append(did)
            info.latency_ms["total"] = round((time.perf_counter() - t_total) * 1000, 1)
            return results, facets, num_found, info

        info.vector_hits = len(vector_docs)

        # Intent inference: classify query and derive per-query RRF weights.
        intent_profile: QueryIntentProfile = infer_intent(
            query_text,
            keyword_alpha=_INTENT_KEYWORD_ALPHA,
            keyword_beta=_INTENT_KEYWORD_BETA,
            mixed_alpha=_INTENT_MIXED_ALPHA,
            mixed_beta=_INTENT_MIXED_BETA,
            semantic_alpha=_INTENT_SEMANTIC_ALPHA,
            semantic_beta=_INTENT_SEMANTIC_BETA,
        )
        info.intent_label = intent_profile.intent_label
        info.alpha = intent_profile.alpha
        info.beta = intent_profile.beta
        info.intent_signals = intent_profile.signals
        logger.debug(
            "Query intent: %s (alpha=%.2f beta=%.2f signals=%s)",
            intent_profile.intent_label,
            intent_profile.alpha,
            intent_profile.beta,
            intent_profile.signals,
        )

        # Stage 3: RRF fusion at document level.
        # Lexical results are chunk records; collapse to unique doc_ids in
        # rank order (first occurrence of each doc_id wins).
        # Vector docs have already been collapsed by doc_id in _vector_retrieval.
        t0 = time.perf_counter()
        seen_lex: set[str] = set()
        lexical_ids: list[str] = []
        lex_docs_by_doc_id: dict[str, dict] = {}
        for d in lexical_docs:
            did = d.get("doc_id") or d.get("id")
            if did and did not in seen_lex:
                seen_lex.add(did)
                lexical_ids.append(did)
                lex_docs_by_doc_id[did] = d

        vector_doc_ids = [d["doc_id"] for d in vector_docs]
        fused = reciprocal_rank_fusion(
            lexical_ids,
            vector_doc_ids,
            HYBRID_RRF_K,
            lexical_weight=intent_profile.alpha,
            vector_weight=intent_profile.beta,
        )
        info.latency_ms["rrf"] = round((time.perf_counter() - t0) * 1000, 1)
        info.fused_hits = len(fused)
        # Capture the full fused doc_id list (before top-K slicing) so analytics
        # can aggregate over the complete matched population rather than just the
        # lexical BM25 candidates.
        info.fused_doc_ids = [fid for fid, _ in fused]

        # Build doc-level metadata map from fused ranking.
        vec_docs_by_doc_id: dict[str, dict] = {d["doc_id"]: d for d in vector_docs}
        lexical_id_set = set(lexical_ids)
        vector_doc_id_set = set(vector_doc_ids)

        # Ordered list of (doc_id, rrf_score) for the top-K fused docs.
        fused_top: list[tuple[str, float]] = []
        fused_rrf: dict[str, float] = {}
        fused_source: dict[str, str] = {}
        for fused_id, rrf_score in fused[: HYBRID_RERANK_K]:
            doc = lex_docs_by_doc_id.get(fused_id) or vec_docs_by_doc_id.get(fused_id)
            if doc is None:
                continue
            in_lex = fused_id in lexical_id_set
            in_vec = fused_id in vector_doc_id_set
            fused_top.append((fused_id, rrf_score))
            fused_rrf[fused_id] = rrf_score
            fused_source[fused_id] = "both" if (in_lex and in_vec) else ("lexical" if in_lex else "vector")

        # Stage 4a: expand each fused doc_id to all its chunks for reranking.
        # Each doc_id appears exactly once in fused_top, so chunk expansion is
        # safe — no duplicate chunks are produced.
        t0 = time.perf_counter()
        chunk_pool = self._fetch_chunks_for_reranking(
            [did for did, _ in fused_top],
            fused_rrf,
            fused_source,
            lex_docs_by_doc_id,
            vec_docs_by_doc_id,
        )
        info.latency_ms["chunk_expand"] = round((time.perf_counter() - t0) * 1000, 1)

        # Stage 4b: rerank all chunks, then max-pool to doc level.
        # Build concept-aware reranker query text so the cross-encoder sees the
        # same concept split that the embedding stage used.
        if concept_text and concept_text.strip():
            reranker_query = f"{query_text}\nConcepts: {concept_text}"
        else:
            reranker_query = query_text
        t0 = time.perf_counter()
        reranked_chunks = self._reranker.rerank(
            reranker_query, chunk_pool, top_k=HYBRID_RERANK_CHUNK_K
        )
        info.latency_ms["rerank"] = round((time.perf_counter() - t0) * 1000, 1)

        if reranked_chunks is None:
            # Reranker failed → degrade to RRF order at doc level
            info.degraded = True
            info.warnings.append("Reranker unavailable; serving RRF-ranked results.")
            # Reconstruct a doc-level pool in RRF order as fallback
            reranked: list[Candidate] = []
            seen_fallback: set[str] = set()
            for did, rrf_score in fused_top:
                doc = lex_docs_by_doc_id.get(did) or vec_docs_by_doc_id.get(did)
                if doc is None or did in seen_fallback:
                    continue
                seen_fallback.add(did)
                reranked.append(Candidate(
                    id=did,
                    doc_id=did,
                    source=fused_source[did],
                    raw_score=float(doc.get("score", 0.0)),
                    rrf_score=rrf_score,
                    display_fields=doc,
                ))
        else:
            # Max-pool chunk rerank scores to doc level: best chunk wins.
            best_by_doc: dict[str, Candidate] = {}
            for chunk_cand in reranked_chunks:
                did = chunk_cand.doc_id
                if did not in best_by_doc or chunk_cand.rerank_score > best_by_doc[did].rerank_score:
                    best_by_doc[did] = chunk_cand
            # Sort docs by their best chunk's rerank score descending, then
            # slice to the top-K for display.
            reranked = sorted(best_by_doc.values(), key=lambda c: c.rerank_score, reverse=True)
            reranked = reranked[:HYBRID_RERANK_TOP_K]

        info.reranked_hits = len(reranked)

        # Stage 5: apply requested sort to the final candidate set, then fetch
        # docs with highlighting from Solr.
        # final_ids are doc_ids (stable source-document ids), so the id filter
        # must match against the doc_id field for chunk records.
        t0 = time.perf_counter()

        if _sort_policy(sort) == "recency":
            # Re-order candidates by created_date desc; semantic score is the tie-breaker.
            def _parse_date(cand: Candidate) -> str:
                # ISO-8601 date strings sort lexicographically; missing/empty sorts last.
                date_val = cand.display_fields.get("created_date", "")
                return date_val if date_val else ""

            reranked = sorted(
                reranked,
                key=lambda c: (
                    _parse_date(c),
                    c.rerank_score if c.rerank_score != 0.0 else c.rrf_score,
                ),
                reverse=True,
            )

        final_candidates = reranked
        final_ids = [c.doc_id for c in final_candidates]
        # Build a score map: prefer rerank score; fall back to RRF score.
        pipeline_scores = {
            c.doc_id: (c.rerank_score if c.rerank_score != 0.0 else c.rrf_score)
            for c in final_candidates
        }
        results, _ = self._fetch_with_highlighting(
            final_ids, solr_q, fq, qf, pf, bq, use_nlp, pipeline_scores, sort
        )
        # Compute facets from the actual result set so sidebar counts match
        # what is displayed, not the wider lexical candidate pool.
        facets = _facets_from_results(results)
        info.latency_ms["highlight_fetch"] = round((time.perf_counter() - t0) * 1000, 1)

        # Replace the earlier full-fused list with the reranker top-K so that
        # analytics aggregates over exactly the same set the user sees.
        info.fused_doc_ids = final_ids

        info.latency_ms["total"] = round((time.perf_counter() - t_total) * 1000, 1)
        return results, facets, num_found, info

    # ------------------------------------------------------------------
    # Internal stages
    # ------------------------------------------------------------------

    def _lexical_retrieval(
        self,
        solr_q: str,
        fq: list[str],
        qf: str,
        pf: str,
        bq: list[str],
        sort: str,
        use_nlp: bool,
    ) -> tuple[list[dict], dict, int]:
        """Fetch up to HYBRID_LEXICAL_K candidates via eDisMax."""
        params: dict[str, Any] = {
            "q":       solr_q,
            "defType": "edismax",
            "qf":      qf,
            "pf":      pf,
            "mm":      "3<75%",
            "fl":      DISPLAY_FIELDS,
            "rows":    HYBRID_LEXICAL_K,
            "start":   0,
            "wt":      "json",
            "json.facet": _json_facet_payload(),
            "sort":  sort,
            "boost": "product(upvote_log,0.1)",
        }
        if bq:
            params["bq"] = bq
        all_fq = list(fq or [])
        all_fq.append(_collapse_filter(sort))
        params["fq"] = all_fq

        resp = requests.get(self._solr_url, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        docs = payload.get("response", {}).get("docs", [])
        facets, unique_doc_count = _parse_doc_facets(payload)
        num_found = unique_doc_count if unique_doc_count is not None else payload.get("response", {}).get("numFound", 0)
        return docs, facets, num_found

    def _vector_retrieval(
        self,
        query_text: str,
        fq: list[str],
        concept_text: str = "",
    ) -> tuple[list[dict] | None, dict[str, str]]:
        """Embed query and issue Solr kNN query against chunk_vector.

        Uses the dual-path composition formula:
            query_combined = normalize(f(a+b) + f(b))
        where:
            f(a+b) = embedding of the full query text (query_text)
            f(b)   = embedding of the concept-only text (concept_text)

        When concept_text is empty, f(b) is the zero vector and the combined
        vector reduces to the normalised main embedding.

        Collapses chunk hits to one representative record per source document
        (best chunk score wins).

        Returns:
            (collapsed_docs, best_chunk_texts) where:
              - collapsed_docs is a list of one doc per unique doc_id (None on failure)
              - best_chunk_texts maps doc_id → best-matching chunk_text
        """
        main_embedding = self._embedder.embed_query(query_text)
        if main_embedding is None:
            return None, {}

        dim = len(main_embedding)

        if concept_text and concept_text.strip():
            concept_embedding = self._embedder.embed_query(concept_text)
            if concept_embedding is None:
                logger.warning(
                    "Concept embedding failed; falling back to main-only query vector."
                )
                concept_embedding = [0.0] * dim
        else:
            concept_embedding = [0.0] * dim

        embedding = _combine_vectors(main_embedding, concept_embedding)

        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
        params: dict[str, Any] = {
            "q":    f"{{!knn f=chunk_vector topK={HYBRID_VECTOR_K}}}{vec_str}",
            "fl":   CHUNK_VECTOR_FIELDS,
            "rows": HYBRID_VECTOR_K,
            "wt":   "json",
        }
        if fq:
            params["fq"] = fq

        try:
            resp = requests.post(self._solr_url, data=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            chunk_hits = payload.get("response", {}).get("docs", [])
        except requests.RequestException as exc:
            logger.warning("Vector retrieval Solr query failed: %s", exc)
            return None, {}

        # Collapse chunk hits by doc_id, keeping the first (highest-score) hit
        # per source document.  Solr returns kNN results in descending score order,
        # so the first occurrence of each doc_id is the best chunk.
        seen_doc_ids: set[str] = set()
        collapsed: list[dict] = []
        best_chunk_texts: dict[str, str] = {}

        for chunk in chunk_hits:
            # For chunk records doc_id is set explicitly; fall back to id for
            # legacy documents that predate chunking.
            doc_id = chunk.get("doc_id") or chunk.get("id")
            if not doc_id or doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)
            # Store a representative document for the doc_id
            representative = dict(chunk)
            representative["doc_id"] = doc_id
            collapsed.append(representative)
            chunk_text = chunk.get("chunk_text", "")
            if chunk_text:
                best_chunk_texts[doc_id] = chunk_text

        return collapsed, best_chunk_texts

    def _fetch_chunks_for_reranking(
        self,
        doc_ids: list[str],
        fused_rrf: dict[str, float],
        fused_source: dict[str, str],
        lex_docs_by_doc_id: dict[str, dict],
        vec_docs_by_doc_id: dict[str, dict],
    ) -> list[Candidate]:
        """Fetch all chunks for each doc_id and return a flat Candidate list.

        Each doc_id in `doc_ids` is expanded to all its Solr chunk records.
        Since doc_ids come from the already-deduplicated RRF fused list, each
        doc_id appears exactly once — no duplicate chunks are produced.

        Falls back to the single representative record already in memory if
        the Solr fetch fails.
        """
        if not doc_ids:
            return []

        id_filter = "doc_id:(" + " OR ".join(doc_ids) + ")"
        params: dict[str, Any] = {
            "q":    "*:*",
            "fl":   "id,doc_id,score,chunk_text,chunk_concept_text,chunk_index,search_text",
            "rows": HYBRID_RERANK_CHUNK_K,
            "wt":   "json",
            "fq":   id_filter,
        }
        try:
            resp = requests.get(self._solr_url, params=params, timeout=15)
            resp.raise_for_status()
            chunk_hits = resp.json().get("response", {}).get("docs", [])
        except requests.RequestException as exc:
            logger.warning("Chunk fetch for reranking failed: %s", exc)
            chunk_hits = []

        def _reranker_doc_text(chunk_text: str, chunk_concept_text: str) -> str:
            """Build concept-aware document text for the cross-encoder reranker.

            Appends a compact concept section so the reranker sees the same
            concept signal that was used during dual-path embedding.
            """
            if chunk_concept_text and chunk_concept_text.strip():
                return f"{chunk_text}\nConcepts: {chunk_concept_text}"
            return chunk_text

        if not chunk_hits:
            # Fallback: one candidate per doc using the representative record
            candidates = []
            for did in doc_ids:
                doc = lex_docs_by_doc_id.get(did) or vec_docs_by_doc_id.get(did)
                if doc is None:
                    continue
                chunk_text = doc.get("chunk_text", "") or doc.get("search_text", "")
                chunk_concept_text = doc.get("chunk_concept_text", "")
                candidates.append(Candidate(
                    id=doc.get("id", did),
                    doc_id=did,
                    source=fused_source.get(did, "lexical"),
                    raw_score=float(doc.get("score", 0.0)),
                    rrf_score=fused_rrf.get(did, 0.0),
                    search_text=_reranker_doc_text(chunk_text, chunk_concept_text),
                    display_fields=doc,
                ))
            return candidates

        # Build one Candidate per chunk.
        # display_fields is taken from the in-memory representative record for
        # the doc (title, body, metadata etc.) — chunk records only add
        # chunk_text/chunk_concept_text and chunk_index on top.
        candidates = []
        for chunk in chunk_hits:
            did = chunk.get("doc_id") or chunk.get("id")
            if not did:
                continue
            doc = lex_docs_by_doc_id.get(did) or vec_docs_by_doc_id.get(did) or chunk
            chunk_text = chunk.get("chunk_text", "") or chunk.get("search_text", "")
            chunk_concept_text = chunk.get("chunk_concept_text", "")
            candidates.append(Candidate(
                id=chunk.get("id", did),
                doc_id=did,
                source=fused_source.get(did, "lexical"),
                raw_score=float(chunk.get("score", doc.get("score", 0.0))),
                rrf_score=fused_rrf.get(did, 0.0),
                search_text=_reranker_doc_text(chunk_text, chunk_concept_text),
                display_fields=doc,
            ))
        return candidates

    def _fetch_with_highlighting(
        self,
        doc_ids: list[str],
        solr_q: str,
        fq: list[str],
        qf: str,
        pf: str,
        bq: list[str],
        use_nlp: bool,
        pipeline_scores: dict[str, float] | None = None,
        sort: str = "score desc",
    ) -> tuple[list[dict], dict]:
        """Fetch one representative chunk record per doc_id with highlighting.

        Since records are stored as chunks, the Solr `id` is the chunk_id and
        the stable source identity lives in the `doc_id` field.  We filter on
        `doc_id` and pick the chunk with chunk_index=0 (the first/canonical
        chunk) for display, falling back to whichever chunk Solr returns first.

        ``sort`` controls which chunk is picked as the representative when a
        document has multiple chunks:
          - ``score desc``        → highest-scoring chunk (relevance)
          - ``created_date desc`` → chunk from the most recent date bucket
        """
        if not doc_ids:
            return [], {}

        # For the collapse filter use the requested sort so the representative
        # chunk matches what the user asked for.
        collapse_sort = "created_date desc" if _sort_policy(sort) == "recency" else "score desc"
        id_filter = "doc_id:(" + " OR ".join(doc_ids) + ")"
        all_fq = (fq or []) + [id_filter, _collapse_filter(collapse_sort)]

        # Use q=*:* so that all doc_ids are guaranteed to be returned regardless
        # of lexical match strength (vector-only results would otherwise be
        # dropped by the mm minimum-match filter).  Build hl.q using the
        # standard lucene parser with explicit field targeting — edismax as
        # hl.qparser does not reliably apply hl.qf in all Solr versions.
        hl_fields = ("search_text", "body", "title")
        if solr_q and solr_q.strip() and solr_q.strip() != "*:*":
            hl_q = " OR ".join(f"{f}:({solr_q})" for f in hl_fields)
        else:
            hl_q = solr_q or "*:*"
        params: dict[str, Any] = {
            "q":       "*:*",
            "fl":      DISPLAY_FIELDS + ",chunk_index",
            "rows":    len(doc_ids),
            "wt":      "json",
            "hl":      "true",
            "hl.q":    hl_q,
            "hl.fl":   "search_text,body,title",
            "hl.simple.pre":  "<mark>",
            "hl.simple.post": "</mark>",
            "fq":      all_fq,
        }

        try:
            resp = requests.get(self._solr_url, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            logger.warning("Highlight fetch failed: %s", exc)
            return [], {}

        raw_docs = payload.get("response", {}).get("docs", [])
        highlighting = payload.get("highlighting", {})
        facets, _ = _parse_doc_facets(payload)
        docs_by_doc_id = {
            (doc.get("doc_id") or doc.get("id")): doc
            for doc in raw_docs
            if (doc.get("doc_id") or doc.get("id"))
        }

        results = []
        for did in doc_ids:
            display_doc = docs_by_doc_id.get(did)
            if display_doc is None:
                continue
            chunk_solr_id = display_doc.get("id", "")
            hl = highlighting.get(chunk_solr_id, {})
            snippet = ""
            for fn in ("search_text", "body", "title", "lemmatized_text", "concepts"):
                if hl.get(fn):
                    snippet = hl[fn][0]
                    break
            if not snippet:
                snippet = (display_doc.get("body") or display_doc.get("title") or "")[:260]
            result = {**display_doc, "snippet": snippet}
            if pipeline_scores and did in pipeline_scores:
                result["score"] = round(pipeline_scores[did], 4)
            results.append(result)

        return results, facets

    # ------------------------------------------------------------------
    # Analytics aggregation (query-scoped dashboard)
    # ------------------------------------------------------------------

    # Top-N defaults for grouped breakdowns
    _SUBREDDIT_TOP_N = 8
    _MODEL_TOP_N     = 6
    _VENDOR_TOP_N    = 5
    # Minimum document count before a comparison section is shown in the UI
    _MIN_SECTION_DOCS = 3

    def get_analytics(
        self,
        solr_q: str,
        fq: list[str],
        qf: str,
        pf: str,
        bq: list[str],
        date_from: str = "",
        date_to: str = "",
        doc_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Aggregate a full dashboard payload for the matched document set.

        When ``doc_ids`` is provided (the full fused doc_id list from the hybrid
        pipeline) the query uses ``q=*:* fq=doc_id:(...)`` so that vector-only
        results are included.  Without ``doc_ids`` the query falls back to
        replaying the lexical eDisMax query.

        Bucket granularity is chosen automatically:
          - If both ``date_from`` and ``date_to`` are supplied and the window
            is ≤ 31 days → daily buckets (gap ``+1DAY``).
          - Otherwise → monthly buckets (gap ``+1MONTH``).

        Returns a structured dict with sections:
          ``overview``            total_docs, date_span, avg_score
          ``sentiment``           polarity/subjectivity totals + time series
          ``by_subreddit``        top-N subreddit counts + sentiment mix
          ``by_model``            top-N model counts + sentiment mix
          ``by_vendor``           top-N vendor counts + sentiment mix
          ``by_type``             post vs comment volume + sentiment mix
          ``score_bands``         fixed score ranges + polarity split
          ``confidence_bands``    polarity/subjectivity confidence distributions
          ``total_docs_analysed`` total unique docs matched (convenience top-level key)
          legacy flat keys for backwards compatibility with existing template code
        On any Solr error returns an empty dict so callers can degrade gracefully.
        """
        # --- date granularity ---
        gap = "+1MONTH"
        if date_from and date_to:
            try:
                from datetime import date as _date
                d_from = _date.fromisoformat(date_from)
                d_to   = _date.fromisoformat(date_to)
                if (d_to - d_from).days <= 31:
                    gap = "+1DAY"
            except ValueError:
                pass

        facet_start = (date_from + "T00:00:00Z") if date_from else "1970-01-01T00:00:00Z"
        facet_end   = (date_to   + "T23:59:59Z") if date_to   else "NOW"

        polarity_labels     = ["positive", "negative", "neutral", "mixed"]
        subjectivity_labels = ["subjective", "objective"]

        # Nested polarity breakdown reused under each grouped facet
        _nested_polarity = {
            "type": "terms",
            "field": "polarity_label",
            "limit": -1,
            "mincount": 0,
            "missing": True,
            "facet": {"docs": "unique(doc_id)"},
        }

        # JSON Facet payload covering all dashboard sections in a single Solr round-trip.
        json_facet = json.dumps({
            # Scalar aggregates
            "total_unique_docs": "unique(doc_id)",
            "avg_score": "avg(score)",
            "min_date": "min(created_date)",
            "max_date": "max(created_date)",
            # Sentiment totals
            "polarity_totals": {
                "type": "terms", "field": "polarity_label",
                "limit": -1, "mincount": 0, "missing": True,
                "facet": {"docs": "unique(doc_id)"},
            },
            "subjectivity_totals": {
                "type": "terms", "field": "subjectivity_label",
                "limit": -1, "mincount": 0, "missing": True,
                "facet": {"docs": "unique(doc_id)"},
            },
            # Time series
            "by_date": {
                "type": "range", "field": "created_date",
                "start": facet_start, "end": facet_end, "gap": gap,
                "mincount": 1,
                "facet": {
                    "polarity":     dict(_nested_polarity),
                    "subjectivity": {
                        "type": "terms", "field": "subjectivity_label",
                        "limit": -1, "mincount": 0, "missing": True,
                        "facet": {"docs": "unique(doc_id)"},
                    },
                    "volume": "unique(doc_id)",
                },
            },
            # Grouped breakdowns
            "by_subreddit": {
                "type": "terms", "field": "subreddit",
                "limit": self._SUBREDDIT_TOP_N, "mincount": 1,
                "facet": {
                    "docs": "unique(doc_id)",
                    "polarity": dict(_nested_polarity),
                },
            },
            "by_model": {
                "type": "terms", "field": "model_mentions",
                "limit": self._MODEL_TOP_N, "mincount": 1,
                "facet": {
                    "docs": "unique(doc_id)",
                    "polarity": dict(_nested_polarity),
                },
            },
            "by_vendor": {
                "type": "terms", "field": "vendor_mentions",
                "limit": self._VENDOR_TOP_N, "mincount": 1,
                "facet": {
                    "docs": "unique(doc_id)",
                    "polarity": dict(_nested_polarity),
                },
            },
            "by_type": {
                "type": "terms", "field": "type",
                "limit": -1, "mincount": 1,
                "facet": {
                    "docs": "unique(doc_id)",
                    "polarity": dict(_nested_polarity),
                },
            },
            # Confidence distributions (no nesting needed — just term counts)
            "polarity_confidence_bins": {
                "type": "range", "field": "polarity_confidence",
                "start": 0.0, "end": 1.0, "gap": 0.1,
                "mincount": 1,
                "facet": {"docs": "unique(doc_id)"},
            },
            "subjectivity_confidence_bins": {
                "type": "range", "field": "subjectivity_confidence",
                "start": 0.0, "end": 1.0, "gap": 0.1,
                "mincount": 1,
                "facet": {"docs": "unique(doc_id)"},
            },
        }, separators=(",", ":"))

        # Build Solr query params (doc_id fast-path or lexical fallback)
        BATCH = 1000
        if doc_ids:
            all_fq = list(fq or [])
            if len(doc_ids) <= BATCH:
                all_fq.append("doc_id:(" + " OR ".join(doc_ids) + ")")
            else:
                terms_val = ",".join(doc_ids)
                all_fq.append(f"{{!terms f=doc_id}}{terms_val}")
            all_fq.append(_collapse_filter("score desc"))
            params: dict[str, Any] = {
                "q":          "*:*",
                "rows":       0,
                "wt":         "json",
                "json.facet": json_facet,
                "fq":         all_fq,
            }
        else:
            params = {
                "q":          solr_q,
                "defType":    "edismax",
                "qf":         qf,
                "pf":         pf,
                "mm":         "3<75%",
                "rows":       0,
                "wt":         "json",
                "json.facet": json_facet,
            }
            if bq:
                params["bq"] = bq
            all_fq = list(fq or [])
            all_fq.append(_collapse_filter("score desc"))
            params["fq"] = all_fq

        try:
            resp = requests.post(self._solr_url, data=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            logger.warning("Analytics Solr query failed: %s", exc)
            return {}

        facets = payload.get("facets", {})
        if not facets:
            return {}

        # ----------------------------------------------------------------
        # Helper: extract label → count dict from a terms facet node
        # ----------------------------------------------------------------
        def _extract_totals(facet_node: Any, labels: list[str]) -> dict[str, int]:
            totals: dict[str, int] = {lbl: 0 for lbl in labels}
            totals["unknown"] = 0
            if not isinstance(facet_node, dict):
                return totals
            for bucket in facet_node.get("buckets", []):
                val   = str(bucket.get("val", "")).strip().lower()
                count = int(bucket.get("docs", bucket.get("count", 0)) or 0)
                if val in totals:
                    totals[val] = count
                else:
                    totals["unknown"] += count
            missing_count = int(
                (facet_node.get("missing") or {}).get("docs",
                (facet_node.get("missing") or {}).get("count", 0)) or 0
            )
            totals["unknown"] += missing_count
            return totals

        # ----------------------------------------------------------------
        # Helper: build top-N breakdown list from a grouped terms facet node.
        # Returns a list of dicts: [{label, count, polarity_mix}, ...]
        # ----------------------------------------------------------------
        def _extract_grouped(facet_node: Any, top_n: int) -> list[dict[str, Any]]:
            if not isinstance(facet_node, dict):
                return []
            result: list[dict[str, Any]] = []
            other_count = 0
            for bucket in facet_node.get("buckets", []):
                label = str(bucket.get("val", "")).strip()
                if not label:
                    continue
                count = int(bucket.get("docs", bucket.get("count", 0)) or 0)
                pol_node = bucket.get("polarity", {})
                pol_mix = _extract_totals(pol_node, polarity_labels)
                result.append({"label": label, "count": count, "polarity_mix": pol_mix})
            # Collapse tail into "Other" if top_n < total buckets
            if len(result) > top_n:
                tail = result[top_n:]
                other_count = sum(r["count"] for r in tail)
                result = result[:top_n]
                if other_count:
                    result.append({"label": "Other", "count": other_count, "polarity_mix": {lbl: 0 for lbl in polarity_labels + ["unknown"]}})
            return result

        # ----------------------------------------------------------------
        # Helper: extract confidence bin data from a range facet node.
        # Returns {labels: [...], counts: [...]}
        # ----------------------------------------------------------------
        def _extract_confidence_bins(facet_node: Any) -> dict[str, Any]:
            if not isinstance(facet_node, dict):
                return {"labels": [], "counts": []}
            labels: list[str] = []
            counts: list[int] = []
            for bucket in facet_node.get("buckets", []):
                lo = bucket.get("val", 0.0)
                count = int(bucket.get("docs", bucket.get("count", 0)) or 0)
                labels.append(f"{lo:.1f}–{lo+0.1:.1f}")
                counts.append(count)
            return {"labels": labels, "counts": counts}

        # ----------------------------------------------------------------
        # Scalars
        # ----------------------------------------------------------------
        total_docs: int = int(facets.get("total_unique_docs", 0) or 0)
        avg_score_raw = facets.get("avg_score")
        avg_score: float | None = round(float(avg_score_raw), 2) if avg_score_raw is not None else None
        min_date = str(facets.get("min_date", "") or "")[:10] or None
        max_date = str(facets.get("max_date", "") or "")[:10] or None

        # ----------------------------------------------------------------
        # Sentiment totals
        # ----------------------------------------------------------------
        polarity_totals     = _extract_totals(facets.get("polarity_totals"),     polarity_labels)
        subjectivity_totals = _extract_totals(facets.get("subjectivity_totals"), subjectivity_labels)

        # ----------------------------------------------------------------
        # Time series
        # ----------------------------------------------------------------
        by_date_node = facets.get("by_date", {})
        date_buckets_raw = by_date_node.get("buckets", []) if isinstance(by_date_node, dict) else []

        time_buckets: list[str] = []
        volume_series: list[int] = []
        polarity_series: dict[str, list[int]] = {lbl: [] for lbl in polarity_labels + ["unknown"]}
        subjectivity_series: dict[str, list[int]] = {lbl: [] for lbl in subjectivity_labels + ["unknown"]}

        for bucket in date_buckets_raw:
            date_val = bucket.get("val", "")
            if not date_val:
                continue
            date_str = str(date_val)[:10]
            time_buckets.append(date_str)
            volume_series.append(int(bucket.get("volume", bucket.get("count", 0)) or 0))

            pol_node = bucket.get("polarity", {})
            pol_counts: dict[str, int] = {lbl: 0 for lbl in polarity_labels + ["unknown"]}
            for pb in (pol_node.get("buckets", []) if isinstance(pol_node, dict) else []):
                lbl = str(pb.get("val", "")).strip().lower()
                cnt = int(pb.get("docs", pb.get("count", 0)) or 0)
                if lbl in pol_counts:
                    pol_counts[lbl] = cnt
                else:
                    pol_counts["unknown"] += cnt
            missing_pol = int(
                (pol_node.get("missing") or {}).get("docs",
                (pol_node.get("missing") or {}).get("count", 0)) or 0
            ) if isinstance(pol_node, dict) else 0
            pol_counts["unknown"] += missing_pol
            for lbl in polarity_series:
                polarity_series[lbl].append(pol_counts.get(lbl, 0))

            subj_node = bucket.get("subjectivity", {})
            subj_counts: dict[str, int] = {lbl: 0 for lbl in subjectivity_labels + ["unknown"]}
            for sb in (subj_node.get("buckets", []) if isinstance(subj_node, dict) else []):
                lbl = str(sb.get("val", "")).strip().lower()
                cnt = int(sb.get("docs", sb.get("count", 0)) or 0)
                if lbl in subj_counts:
                    subj_counts[lbl] = cnt
                else:
                    subj_counts["unknown"] += cnt
            missing_subj = int(
                (subj_node.get("missing") or {}).get("docs",
                (subj_node.get("missing") or {}).get("count", 0)) or 0
            ) if isinstance(subj_node, dict) else 0
            subj_counts["unknown"] += missing_subj
            for lbl in subjectivity_series:
                subjectivity_series[lbl].append(subj_counts.get(lbl, 0))

        # ----------------------------------------------------------------
        # Grouped breakdowns
        # ----------------------------------------------------------------
        by_subreddit = _extract_grouped(facets.get("by_subreddit"), self._SUBREDDIT_TOP_N)
        by_model     = _extract_grouped(facets.get("by_model"),     self._MODEL_TOP_N)
        by_vendor    = _extract_grouped(facets.get("by_vendor"),    self._VENDOR_TOP_N)
        by_type      = _extract_grouped(facets.get("by_type"),      20)  # type has few values

        # ----------------------------------------------------------------
        # Confidence distributions
        # ----------------------------------------------------------------
        pol_conf_bins  = _extract_confidence_bins(facets.get("polarity_confidence_bins"))
        subj_conf_bins = _extract_confidence_bins(facets.get("subjectivity_confidence_bins"))

        return {
            # Legacy flat keys (backwards compat — template still uses these)
            "time_buckets":         time_buckets,
            "polarity_series":      polarity_series,
            "subjectivity_series":  subjectivity_series,
            "polarity_totals":      polarity_totals,
            "subjectivity_totals":  subjectivity_totals,
            "total_docs_analysed":  total_docs,
            # New structured sections
            "overview": {
                "total_docs": total_docs,
                "avg_score":  avg_score,
                "min_date":   min_date,
                "max_date":   max_date,
            },
            "sentiment": {
                "polarity_totals":      polarity_totals,
                "subjectivity_totals":  subjectivity_totals,
                "time_buckets":         time_buckets,
                "volume_series":        volume_series,
                "polarity_series":      polarity_series,
                "subjectivity_series":  subjectivity_series,
            },
            "by_subreddit": by_subreddit,
            "by_model":     by_model,
            "by_vendor":    by_vendor,
            "by_type":      by_type,
            "confidence_bands": {
                "polarity":     pol_conf_bins,
                "subjectivity": subj_conf_bins,
            },
        }

    # Keep the old name as an alias for callers that haven't migrated yet.
    get_sentiment_analytics = get_analytics

    def _finalize_lexical(
        self,
        lexical_docs: list[dict],
        solr_q: str,
        fq: list[str],
        qf: str = "",
        sort: str = "score desc",
    ) -> list[dict]:
        """Attach snippets to lexical docs (used in degraded mode).

        Lexical docs may be chunk records; collapse to unique doc_ids first.
        ``sort`` is threaded through to ``_fetch_with_highlighting`` so the
        representative chunk collapse honours the requested sort order.
        """
        seen: set[str] = set()
        unique_doc_ids: list[str] = []
        for d in lexical_docs:
            did = d.get("doc_id") or d.get("id")
            if did and did not in seen:
                seen.add(did)
                unique_doc_ids.append(did)
            if len(unique_doc_ids) >= SEARCH_ROWS:
                break

        # Build a score map from the lexical BM25 scores so the displayed
        # score reflects actual relevance rather than the *:* default of 1.0.
        lexical_scores: dict[str, float] = {}
        for d in lexical_docs:
            did = d.get("doc_id") or d.get("id")
            if did and did not in lexical_scores:
                lexical_scores[did] = float(d.get("score", 0.0))

        results, _ = self._fetch_with_highlighting(unique_doc_ids, solr_q, fq, qf, "", [], False, lexical_scores, sort)
        if results:
            return results
        # Fallback: return raw docs without highlights (de-duplicated by doc_id)
        out = []
        seen_fallback: set[str] = set()
        for doc in lexical_docs:
            did = doc.get("doc_id") or doc.get("id")
            if not did or did in seen_fallback:
                continue
            seen_fallback.add(did)
            snippet = (doc.get("body") or doc.get("title") or "")[:260]
            out.append({**doc, "snippet": snippet})
            if len(out) >= SEARCH_ROWS:
                break
        return out
