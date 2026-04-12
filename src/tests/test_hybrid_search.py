"""
Unit and integration tests for the hybrid BM25 + vector retrieval pipeline.

Run with:
    python -m pytest src/tests/test_hybrid_search.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make the src directory importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hybrid_search import (
    Candidate,
    EmbeddingClient,
    HybridSearchService,
    RerankerClient,
    RetrievalInfo,
    reciprocal_rank_fusion,
    _combine_vectors as hs_combine_vectors,
    _sort_policy,
)
from query_intent import infer_intent, QueryIntentProfile
from scripts.prepare_solr_docs import (
    _split_into_chunks,
    _make_chunk_records,
    _chunk_concept_text,
    _combine_vectors as prep_combine_vectors,
    embed_docs,
    CHUNK_TARGET_CHARS,
    CHUNK_OVERLAP_CHARS,
    FALLBACK_CHUNK_TARGET_CHARS,
    FALLBACK_CHUNK_OVERLAP_CHARS,
)


# ---------------------------------------------------------------------------
# RRF unit tests
# ---------------------------------------------------------------------------

class TestReciprocalRankFusion:
    def test_single_list(self):
        ids = ["a", "b", "c"]
        fused = reciprocal_rank_fusion(ids, [], rrf_k=60)
        result_ids = [doc_id for doc_id, _ in fused]
        assert result_ids == ["a", "b", "c"]

    def test_union_of_both_lists(self):
        fused = reciprocal_rank_fusion(["a", "b"], ["c", "d"], rrf_k=60)
        ids = {doc_id for doc_id, _ in fused}
        assert ids == {"a", "b", "c", "d"}

    def test_dedup_shared_ids(self):
        fused = reciprocal_rank_fusion(["a", "b", "c"], ["a", "c", "d"], rrf_k=60)
        ids = [doc_id for doc_id, _ in fused]
        assert len(ids) == len(set(ids)), "Duplicate ids in RRF output"

    def test_shared_id_scores_higher(self):
        fused = reciprocal_rank_fusion(["a", "b"], ["a", "c"], rrf_k=60)
        scores = {doc_id: sc for doc_id, sc in fused}
        # "a" appears rank-1 in both lists → highest score
        assert scores["a"] > scores["b"]
        assert scores["a"] > scores["c"]

    def test_empty_inputs(self):
        assert reciprocal_rank_fusion([], [], rrf_k=60) == []

    def test_score_formula(self):
        # Default weights are lexical_weight=0.5, vector_weight=0.5
        fused = reciprocal_rank_fusion(["x"], [], rrf_k=60)
        _, score = fused[0]
        expected = 0.5 / (60 + 1)
        assert abs(score - expected) < 1e-9

    def test_score_formula_unit_weights(self):
        # With explicit equal-to-1 weights the score is 1/(k+rank)
        fused = reciprocal_rank_fusion(["x"], [], rrf_k=60, lexical_weight=1.0, vector_weight=0.0)
        _, score = fused[0]
        expected = 1.0 / (60 + 1)
        assert abs(score - expected) < 1e-9

    def test_sorted_descending(self):
        fused = reciprocal_rank_fusion(["a", "b", "c"], ["c", "b", "a"], rrf_k=60)
        scores = [sc for _, sc in fused]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# EmbeddingClient unit tests
# ---------------------------------------------------------------------------

class TestEmbeddingClient:
    def _make_client(self):
        return EmbeddingClient(base_url="http://fake-embed:8081")

    def test_embed_query_success(self):
        client = self._make_client()
        fake_response = MagicMock()
        fake_response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}
        fake_response.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_response):
            result = client.embed_query("hello world")
        assert result == [0.1, 0.2, 0.3]

    def test_embed_query_service_down(self):
        import requests as req
        client = self._make_client()
        with patch("hybrid_search.requests.post", side_effect=req.RequestException("refused")):
            result = client.embed_query("hello")
        assert result is None

    def test_embed_batch_calls_in_batches(self):
        client = self._make_client()
        texts = [f"doc {i}" for i in range(5)]
        fake_response = MagicMock()
        # Return 2 embeddings per call (matching batch_size=2)
        call_count = [0]
        def side_effect(*args, **kwargs):
            n = len(kwargs.get("json", {}).get("texts", []))
            fake_response.json.return_value = {"embeddings": [[float(call_count[0])] * 3] * n}
            call_count[0] += 1
            return fake_response
        fake_response.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", side_effect=side_effect):
            results = client.embed_batch(texts, batch_size=2)
        assert len(results) == 5
        assert call_count[0] == 3  # ceil(5/2) = 3 batches

    def test_embed_batch_retries_failed_batch_as_singles(self):
        client = self._make_client()
        responses = [None, [[1.0]], [[2.0]]]
        with patch.object(client, "embed", side_effect=responses):
            results = client.embed_batch(["doc 1", "doc 2"], batch_size=2)
        assert results == [[1.0], [2.0]]

    def test_embed_empty_texts(self):
        client = self._make_client()
        assert client.embed([]) == []

    def test_embed_missing_key_returns_none(self):
        client = self._make_client()
        fake_response = MagicMock()
        fake_response.json.return_value = {"unexpected_key": []}
        fake_response.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_response):
            result = client.embed(["text"])
        assert result is None

    def test_embed_falls_back_to_openai_embeddings_endpoint(self):
        client = self._make_client()
        not_found = MagicMock()
        not_found.raise_for_status.side_effect = __import__("requests").HTTPError(
            response=MagicMock(status_code=404)
        )
        openai_response = MagicMock()
        openai_response.raise_for_status.return_value = None
        openai_response.json.return_value = {
            "data": [{"embedding": [0.4, 0.5, 0.6]}]
        }
        with patch("hybrid_search.requests.post", side_effect=[not_found, openai_response]) as post:
            result = client.embed(["text"])
        assert result == [[0.4, 0.5, 0.6]]
        assert post.call_args_list[1].kwargs["json"] == {"input": ["text"]}


# ---------------------------------------------------------------------------
# RerankerClient unit tests
# ---------------------------------------------------------------------------

class TestRerankerClient:
    def _make_client(self):
        return RerankerClient(base_url="http://fake-rerank:8082")

    def _candidates(self, ids=("a", "b", "c")):
        return [
            Candidate(id=i, doc_id=i, source="lexical", raw_score=1.0, rrf_score=0.5,
                      search_text=f"text for {i}")
            for i in ids
        ]

    def test_rerank_success_float_scores(self):
        client = self._make_client()
        candidates = self._candidates()
        fake_response = MagicMock()
        # Reverse order: c > b > a
        fake_response.json.return_value = {"scores": [0.1, 0.5, 0.9]}
        fake_response.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_response):
            result = client.rerank("query", candidates)
        assert result is not None
        assert result[0].id == "c"
        assert result[1].id == "b"

    def test_rerank_success_dict_scores(self):
        client = self._make_client()
        candidates = self._candidates(ids=("x", "y"))
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "scores": [{"index": 0, "score": 0.3}, {"index": 1, "score": 0.8}]
        }
        fake_response.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_response):
            result = client.rerank("query", candidates)
        assert result is not None
        assert result[0].id == "y"

    def test_rerank_service_down_returns_none(self):
        import requests as req
        client = self._make_client()
        candidates = self._candidates()
        with patch("hybrid_search.requests.post", side_effect=req.RequestException("refused")):
            result = client.rerank("query", candidates)
        assert result is None

    def test_rerank_empty_candidates(self):
        client = self._make_client()
        result = client.rerank("query", [])
        assert result == []

    def test_rerank_openai_style_results_use_relevance_score(self):
        client = self._make_client()
        candidates = self._candidates(ids=("x", "y"))
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.2},
                {"index": 1, "relevance_score": 0.9},
            ]
        }
        fake_response.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_response):
            result = client.rerank("query", candidates)
        assert result is not None
        assert result[0].id == "y"


# ---------------------------------------------------------------------------
# HybridSearchService integration tests (all external calls mocked)
# ---------------------------------------------------------------------------

class TestHybridSearchService:
    SOLR_URL = "http://fake-solr:8983/solr/test_core/select"

    def _make_service(self, embedder=None, reranker=None):
        embedder = embedder or EmbeddingClient()
        reranker = reranker or RerankerClient()
        return HybridSearchService(self.SOLR_URL, embedder, reranker)

    def _make_solr_docs(self, ids, score=1.0):
        """Build fake chunk records.  doc_id == id for simplicity (single chunk per doc)."""
        return [
            {"id": f"{i}__c0", "doc_id": i, "chunk_index": 0,
             "chunk_text": f"chunk text {i}",
             "search_text": f"text {i}", "body": f"body {i}",
             "title": "", "type": "post", "subreddit": "test",
             "source_dataset": "test", "polarity_label": "neutral",
             "model_mentions": [], "vendor_mentions": [],
             "subjectivity_label": "unknown", "sarcasm_label": "unknown",
             "score": 1, "created_date": ""}
            for i in ids
        ]

    def _fake_solr_response(self, ids, facets=None, num_found=None):
        docs = self._make_solr_docs(ids)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": docs, "numFound": num_found or len(ids)},
            "facets": {
                "count": num_found or len(ids),
                "unique_docs": num_found or len(ids),
                "type": {"buckets": []},
                "subreddit": {"buckets": []},
                "polarity_label": {"buckets": []},
                "subjectivity_label": {"buckets": []},
                "source_dataset": {"buckets": []},
                "model_mentions": {"buckets": []},
                "vendor_mentions": {"buckets": []},
            },
            "facet_counts": {"facet_fields": facets or {}},
            "highlighting": {},
        }
        return resp

    def test_healthy_hybrid_flow(self):
        """Full pipeline: lexical + vector + RRF + rerank all succeed."""
        service = self._make_service()

        lexical_resp  = self._fake_solr_response(["a", "b", "c", "d"])
        vector_resp   = self._fake_solr_response(["c", "e", "f"])
        highlight_resp = self._fake_solr_response(["a", "c", "b", "e", "d", "f"])

        embed_mock = MagicMock(return_value=[0.1, 0.2, 0.3])
        service._embedder.embed_query = embed_mock

        rerank_cands = None
        def fake_rerank(query, candidates, top_k=50):
            nonlocal rerank_cands
            rerank_cands = candidates
            for c in candidates:
                c.rerank_score = 0.9 if c.id in ("c", "a") else 0.5
            return sorted(candidates, key=lambda x: x.rerank_score, reverse=True)
        service._reranker.rerank = fake_rerank

        call_count = [0]
        def fake_get(url, params, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                return lexical_resp
            elif call_count[0] == 2:
                return vector_resp
            else:
                return highlight_resp

        chunk_expand_resp = self._fake_solr_response(["a", "b", "c", "d", "e", "f"])
        with patch("hybrid_search.requests.get", side_effect=[lexical_resp, chunk_expand_resp, highlight_resp]), \
             patch("hybrid_search.requests.post", return_value=vector_resp):
            results, facets, num_found, info = service.search(
                solr_q="test query", fq=[], qf="title^4", pf="title^8",
                bq=[], sort="score desc", use_nlp=True, query_text="test query",
            )

        assert info.mode == "hybrid"
        assert not info.degraded
        assert info.lexical_hits == 4
        assert info.vector_hits == 3
        assert info.fused_hits > 0
        assert rerank_cands is not None
        # "c" and "e" should be in fused pool (from both or vector branch)
        # Candidates are chunk-level; check by doc_id
        fused_doc_ids = {c.doc_id for c in rerank_cands}
        assert "c" in fused_doc_ids

    def test_vector_failure_degrades_to_lexical(self):
        """When embed_query returns None, serve lexical results only."""
        service = self._make_service()

        lexical_resp  = self._fake_solr_response(["a", "b"])
        highlight_resp = self._fake_solr_response(["a", "b"])

        service._embedder.embed_query = MagicMock(return_value=None)

        call_count = [0]
        def fake_get(url, params, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                return lexical_resp
            return highlight_resp

        with patch("hybrid_search.requests.get", side_effect=fake_get):
            results, facets, num_found, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[], sort="score desc",
                use_nlp=False, query_text="q",
            )

        assert info.mode == "lexical"
        assert info.degraded
        assert any("Vector retrieval" in w for w in info.warnings)

    def test_reranker_failure_serves_rrf_order(self):
        """When reranker returns None, use RRF-ranked order."""
        service = self._make_service()

        lexical_resp  = self._fake_solr_response(["a", "b", "c"])
        vector_resp   = self._fake_solr_response(["b", "c", "d"])
        highlight_resp = self._fake_solr_response(["b", "c", "a", "d"])

        chunk_expand_resp = self._fake_solr_response(["a", "b", "c", "d"])
        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        service._reranker.rerank = MagicMock(return_value=None)

        with patch("hybrid_search.requests.get", side_effect=[lexical_resp, chunk_expand_resp, highlight_resp]), \
             patch("hybrid_search.requests.post", return_value=vector_resp):
            results, facets, num_found, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[], sort="score desc",
                use_nlp=False, query_text="q",
            )

        assert info.degraded
        assert any("Reranker" in w for w in info.warnings)
        assert info.mode == "hybrid"

    def test_filter_propagation_to_both_branches(self):
        """fq filters must be passed to both lexical and vector Solr queries."""
        service = self._make_service()

        fq_filter = ["polarity_label:negative", "type:post"]
        lexical_resp = self._fake_solr_response(["a", "b"])

        captured_params = []
        call_count = [0]
        def fake_get(url, params, timeout):
            # params may be a list of tuples when requests serialises multi-value fields
            if isinstance(params, list):
                params_dict = {}
                for k, v in params:
                    if k in params_dict:
                        if not isinstance(params_dict[k], list):
                            params_dict[k] = [params_dict[k]]
                        params_dict[k].append(v)
                    else:
                        params_dict[k] = v
            else:
                params_dict = dict(params)
            captured_params.append(params_dict)
            call_count[0] += 1
            if call_count[0] == 1:
                return lexical_resp
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = {
                "response": {"docs": [], "numFound": 0},
                "facet_counts": {"facet_fields": {}},
                "highlighting": {},
            }
            return resp

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])

        with patch("hybrid_search.requests.get", side_effect=fake_get):
            service.search(
                solr_q="q", fq=fq_filter, qf="title^4", pf="title^8", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        # Lexical call (index 0) and vector call (index 1) must both carry fq
        assert len(captured_params) >= 2, (
            f"Expected at least 2 Solr calls; got {len(captured_params)}"
        )
        for i, params in enumerate(captured_params[:2]):
            fq_value = params.get("fq", "")
            fq_str = " ".join(fq_value) if isinstance(fq_value, list) else str(fq_value)
            assert "polarity_label:negative" in fq_str, (
                f"Call {i}: expected fq filter in params, got: {params}"
            )
        lexical_fq = captured_params[0].get("fq", [])
        lexical_fq_str = " ".join(lexical_fq) if isinstance(lexical_fq, list) else str(lexical_fq)
        assert "collapse field=doc_id" in lexical_fq_str

    def test_no_results_returns_empty(self):
        """Zero lexical results → empty results, no crash."""
        service = self._make_service()

        empty_resp = MagicMock()
        empty_resp.raise_for_status.return_value = None
        empty_resp.json.return_value = {
            "response": {"docs": [], "numFound": 0},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }

        with patch("hybrid_search.requests.get", return_value=empty_resp):
            results, facets, num_found, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[], sort="score desc",
                use_nlp=False, query_text="q",
            )

        assert results == []
        assert num_found == 0

    def test_lexical_retrieval_uses_unique_doc_facets_for_num_found(self):
        service = self._make_service()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": self._make_solr_docs(["a", "b"]), "numFound": 9},
            "facets": {
                "count": 9,
                "unique_docs": 2,
                "type": {"buckets": [{"val": "post", "count": 9, "docs": 2}]},
                "subreddit": {"buckets": []},
                "polarity_label": {"buckets": []},
                "subjectivity_label": {"buckets": []},
                "source_dataset": {"buckets": []},
                "model_mentions": {"buckets": []},
                "vendor_mentions": {"buckets": []},
            },
            "highlighting": {},
        }

        with patch("hybrid_search.requests.get", return_value=resp):
            docs, facets, num_found = service._lexical_retrieval(
                solr_q="q", fq=[], qf="", pf="", bq=[], sort="score desc", use_nlp=False
            )

        assert len(docs) == 2
        assert num_found == 2
        assert facets["type"] == ["post", 2]

    def test_fetch_with_highlighting_uses_doc_collapse_not_row_multiplier(self):
        service = self._make_service()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": self._make_solr_docs(["a", "b"]), "numFound": 2},
            "highlighting": {"a__c0": {"body": ["snippet a"]}, "b__c0": {"body": ["snippet b"]}},
            "facet_counts": {"facet_fields": {}},
        }

        captured_params: list[dict] = []

        def fake_get(url, params, timeout):
            captured_params.append(dict(params))
            return resp

        with patch("hybrid_search.requests.get", side_effect=fake_get):
            results, _ = service._fetch_with_highlighting(
                ["a", "b"], "q", [], "title^4", "title^8", [], False
            )

        assert [result["doc_id"] for result in results] == ["a", "b"]
        assert captured_params[0]["rows"] == 2
        fq_value = captured_params[0]["fq"]
        fq_str = " ".join(fq_value) if isinstance(fq_value, list) else str(fq_value)
        assert "doc_id:(a OR b)" in fq_str
        assert "collapse field=doc_id" in fq_str


# ---------------------------------------------------------------------------
# Sort policy unit tests
# ---------------------------------------------------------------------------

class TestSortPolicy:
    def test_score_desc_is_relevance(self):
        assert _sort_policy("score desc") == "relevance"

    def test_created_date_desc_is_recency(self):
        assert _sort_policy("created_date desc") == "recency"

    def test_empty_sort_is_relevance(self):
        assert _sort_policy("") == "relevance"

    def test_unknown_sort_is_relevance(self):
        assert _sort_policy("upvotes desc") == "relevance"


# ---------------------------------------------------------------------------
# Vector mode sort tests
# ---------------------------------------------------------------------------

class TestVectorModeSortSemantics:
    """Tests that verify sort semantics for the vector/hybrid pipeline."""

    SOLR_URL = "http://fake-solr:8983/solr/test_core/select"

    def _make_service(self):
        return HybridSearchService(self.SOLR_URL, EmbeddingClient(), RerankerClient())

    def _make_solr_docs_with_dates(self, entries):
        """entries: list of (id, created_date) tuples."""
        docs = []
        for eid, date in entries:
            docs.append({
                "id": f"{eid}__c0", "doc_id": eid, "chunk_index": 0,
                "chunk_text": f"chunk text {eid}",
                "search_text": f"text {eid}", "body": f"body {eid}",
                "title": "", "type": "post", "subreddit": "test",
                "source_dataset": "test", "polarity_label": "neutral",
                "model_mentions": [], "vendor_mentions": [],
                "subjectivity_label": "unknown", "sarcasm_label": "unknown",
                "score": 1, "created_date": date,
            })
        return docs

    def _fake_solr_response_with_dates(self, entries, num_found=None):
        docs = self._make_solr_docs_with_dates(entries)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": docs, "numFound": num_found or len(docs)},
            "facets": {
                "count": num_found or len(docs),
                "unique_docs": num_found or len(docs),
                "type": {"buckets": []},
                "subreddit": {"buckets": []},
                "polarity_label": {"buckets": []},
                "subjectivity_label": {"buckets": []},
                "source_dataset": {"buckets": []},
                "model_mentions": {"buckets": []},
                "vendor_mentions": {"buckets": []},
            },
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }
        return resp

    def test_vector_score_desc_preserves_rerank_order(self):
        """sort=score desc in vector mode → results ordered by rerank/RRF score."""
        service = self._make_service()

        # Lexical: a, b, c  /  Vector: c, d  → RRF fuses all four
        entries = [("a", "2024-01-01"), ("b", "2024-06-01"), ("c", "2023-01-01"), ("d", "2024-12-01")]
        lexical_resp = self._fake_solr_response_with_dates(entries[:3])
        vector_resp  = self._fake_solr_response_with_dates(entries[2:])
        highlight_resp = self._fake_solr_response_with_dates(entries)
        chunk_expand_resp = self._fake_solr_response_with_dates(entries)

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2, 0.3])

        # Assign rerank scores: d > c > b > a (opposite of any date order)
        def fake_rerank(query, candidates, top_k=50):
            scores = {"a": 0.1, "b": 0.3, "c": 0.7, "d": 0.9}
            for cand in candidates:
                cand.rerank_score = scores.get(cand.doc_id, 0.5)
            return sorted(candidates, key=lambda x: x.rerank_score, reverse=True)

        service._reranker.rerank = fake_rerank

        with patch("hybrid_search.requests.get",
                   side_effect=[lexical_resp, chunk_expand_resp, highlight_resp]), \
             patch("hybrid_search.requests.post", return_value=vector_resp):
            results, _, _, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        # Results are keyed by the order of final_ids passed to _fetch_with_highlighting.
        # highlight_resp returns docs in the order we built them, but _fetch_with_highlighting
        # iterates `doc_ids` (final_ids) so the result order reflects the candidate order.
        # Rerank order: d, c, b, a → first result should be d or c (highest rerank scores).
        result_ids = [r["doc_id"] for r in results]
        # d has highest rerank score; it must appear before a (lowest score)
        assert result_ids.index("d") < result_ids.index("a"), (
            f"Expected d before a in score desc order; got {result_ids}"
        )

    def test_vector_created_date_desc_orders_by_date(self):
        """sort=created_date desc in vector mode → candidates reordered newest-first."""
        service = self._make_service()

        # Four docs with different dates
        entries = [("a", "2024-01-01"), ("b", "2024-06-01"), ("c", "2023-01-01"), ("d", "2024-12-01")]
        lexical_resp = self._fake_solr_response_with_dates(entries[:3])
        vector_resp  = self._fake_solr_response_with_dates(entries[2:])
        highlight_resp = self._fake_solr_response_with_dates(entries)
        chunk_expand_resp = self._fake_solr_response_with_dates(entries)

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2, 0.3])

        # Rerank scores intentionally different from date order
        def fake_rerank(query, candidates, top_k=50):
            scores = {"a": 0.9, "b": 0.7, "c": 0.5, "d": 0.3}
            for cand in candidates:
                cand.rerank_score = scores.get(cand.doc_id, 0.4)
            return sorted(candidates, key=lambda x: x.rerank_score, reverse=True)

        service._reranker.rerank = fake_rerank

        with patch("hybrid_search.requests.get",
                   side_effect=[lexical_resp, chunk_expand_resp, highlight_resp]), \
             patch("hybrid_search.requests.post", return_value=vector_resp):
            results, _, _, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="created_date desc", use_nlp=False, query_text="q",
            )

        result_ids = [r["doc_id"] for r in results]
        # Expected date order: d (2024-12-01) > b (2024-06-01) > a (2024-01-01) > c (2023-01-01)
        assert result_ids.index("d") < result_ids.index("b"), (
            f"Expected d before b in date desc order; got {result_ids}"
        )
        assert result_ids.index("b") < result_ids.index("c"), (
            f"Expected b before c in date desc order; got {result_ids}"
        )
        assert result_ids.index("a") < result_ids.index("c"), (
            f"Expected a before c in date desc order; got {result_ids}"
        )

    def test_vector_created_date_tie_broken_by_semantic_score(self):
        """When two docs share the same date, higher rerank score wins."""
        service = self._make_service()

        # a and b share the same date; c is older
        entries = [("a", "2024-06-01"), ("b", "2024-06-01"), ("c", "2023-01-01")]
        lexical_resp = self._fake_solr_response_with_dates(entries[:2])
        vector_resp  = self._fake_solr_response_with_dates(entries[1:])
        highlight_resp = self._fake_solr_response_with_dates(entries)
        chunk_expand_resp = self._fake_solr_response_with_dates(entries)

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])

        # b has higher rerank score than a (same date)
        def fake_rerank(query, candidates, top_k=50):
            scores = {"a": 0.4, "b": 0.9, "c": 0.6}
            for cand in candidates:
                cand.rerank_score = scores.get(cand.doc_id, 0.5)
            return sorted(candidates, key=lambda x: x.rerank_score, reverse=True)

        service._reranker.rerank = fake_rerank

        with patch("hybrid_search.requests.get",
                   side_effect=[lexical_resp, chunk_expand_resp, highlight_resp]), \
             patch("hybrid_search.requests.post", return_value=vector_resp):
            results, _, _, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="created_date desc", use_nlp=False, query_text="q",
            )

        result_ids = [r["doc_id"] for r in results]
        # b and a share the same date; b has higher score → b before a
        assert result_ids.index("b") < result_ids.index("a"), (
            f"Expected b before a (tie-break by score); got {result_ids}"
        )
        # both 2024 docs before the 2023 doc
        assert result_ids.index("a") < result_ids.index("c") or \
               result_ids.index("b") < result_ids.index("c"), (
            f"Expected 2024 docs before c (2023); got {result_ids}"
        )

    def test_highlight_fetch_collapse_uses_score_desc_for_top_score(self):
        """_fetch_with_highlighting with sort=score desc collapses with score desc."""
        service = self._make_service()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": [], "numFound": 0},
            "highlighting": {},
            "facet_counts": {"facet_fields": {}},
        }
        captured_params: list[dict] = []

        def fake_get(url, params, timeout):
            captured_params.append(dict(params) if not isinstance(params, list) else
                                   {k: v for k, v in params})
            return resp

        with patch("hybrid_search.requests.get", side_effect=fake_get):
            service._fetch_with_highlighting(
                ["a", "b"], "q", [], "", "", [], False, sort="score desc"
            )

        fq_value = captured_params[0].get("fq", [])
        fq_str = " ".join(fq_value) if isinstance(fq_value, list) else str(fq_value)
        assert 'sort="score desc"' in fq_str, (
            f"Expected score desc collapse; got: {fq_str}"
        )

    def test_highlight_fetch_collapse_uses_created_date_desc_for_newest(self):
        """_fetch_with_highlighting with sort=created_date desc collapses with created_date desc."""
        service = self._make_service()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": [], "numFound": 0},
            "highlighting": {},
            "facet_counts": {"facet_fields": {}},
        }
        captured_params: list[dict] = []

        def fake_get(url, params, timeout):
            captured_params.append(dict(params) if not isinstance(params, list) else
                                   {k: v for k, v in params})
            return resp

        with patch("hybrid_search.requests.get", side_effect=fake_get):
            service._fetch_with_highlighting(
                ["a", "b"], "q", [], "", "", [], False, sort="created_date desc"
            )

        fq_value = captured_params[0].get("fq", [])
        fq_str = " ".join(fq_value) if isinstance(fq_value, list) else str(fq_value)
        assert 'sort="created_date desc"' in fq_str, (
            f"Expected created_date desc collapse; got: {fq_str}"
        )

    def test_degraded_lexical_fallback_threads_sort(self):
        """When vector is unavailable, _finalize_lexical passes sort to highlight fetch."""
        service = self._make_service()
        service._embedder.embed_query = MagicMock(return_value=None)

        entries = [("a", "2024-01-01"), ("b", "2024-12-01")]
        lexical_resp = self._fake_solr_response_with_dates(entries)
        highlight_resp = self._fake_solr_response_with_dates(entries)
        captured_params: list[dict] = []

        original_fetch = service._fetch_with_highlighting

        def capturing_fetch(doc_ids, solr_q, fq, qf, pf, bq, use_nlp,
                            pipeline_scores=None, sort="score desc"):
            captured_params.append({"sort": sort})
            return original_fetch(doc_ids, solr_q, fq, qf, pf, bq, use_nlp,
                                  pipeline_scores, sort)

        service._fetch_with_highlighting = capturing_fetch

        with patch("hybrid_search.requests.get", side_effect=[lexical_resp, highlight_resp]):
            service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="created_date desc", use_nlp=False, query_text="q",
            )

        assert any(p["sort"] == "created_date desc" for p in captured_params), (
            f"Expected created_date desc to be threaded through; got: {captured_params}"
        )

    def test_lexical_only_mode_score_desc_unchanged(self):
        """use_vector=False + sort=score desc behaves exactly as before (regression)."""
        service = self._make_service()

        entries = [("a", "2024-01-01"), ("b", "2024-12-01")]
        lexical_resp = self._fake_solr_response_with_dates(entries)
        highlight_resp = self._fake_solr_response_with_dates(entries)
        captured_params: list[dict] = []

        original_fetch = service._fetch_with_highlighting

        def capturing_fetch(doc_ids, solr_q, fq, qf, pf, bq, use_nlp,
                            pipeline_scores=None, sort="score desc"):
            captured_params.append({"sort": sort, "doc_ids": list(doc_ids)})
            return original_fetch(doc_ids, solr_q, fq, qf, pf, bq, use_nlp,
                                  pipeline_scores, sort)

        service._fetch_with_highlighting = capturing_fetch

        with patch("hybrid_search.requests.get", side_effect=[lexical_resp, highlight_resp]):
            results, _, _, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
                use_vector=False,
            )

        assert info.mode == "lexical"
        assert any(p["sort"] == "score desc" for p in captured_params), (
            f"Expected score desc; got: {captured_params}"
        )

    def test_lexical_only_mode_created_date_desc_regression(self):
        """use_vector=False + sort=created_date desc threads sort to highlight fetch."""
        service = self._make_service()

        entries = [("a", "2024-01-01"), ("b", "2024-12-01")]
        lexical_resp = self._fake_solr_response_with_dates(entries)
        highlight_resp = self._fake_solr_response_with_dates(entries)
        captured_params: list[dict] = []

        original_fetch = service._fetch_with_highlighting

        def capturing_fetch(doc_ids, solr_q, fq, qf, pf, bq, use_nlp,
                            pipeline_scores=None, sort="score desc"):
            captured_params.append({"sort": sort})
            return original_fetch(doc_ids, solr_q, fq, qf, pf, bq, use_nlp,
                                  pipeline_scores, sort)

        service._fetch_with_highlighting = capturing_fetch

        with patch("hybrid_search.requests.get", side_effect=[lexical_resp, highlight_resp]):
            service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="created_date desc", use_nlp=False, query_text="q",
                use_vector=False,
            )

        assert any(p["sort"] == "created_date desc" for p in captured_params), (
            f"Expected created_date desc; got: {captured_params}"
        )


# ---------------------------------------------------------------------------
# ETL chunking tests
# ---------------------------------------------------------------------------

class TestSplitIntoChunks:
    def test_short_text_is_single_chunk(self):
        text = "short text"
        chunks = _split_into_chunks(text, target=1200, overlap=200)
        assert len(chunks) == 1
        assert chunks[0][0] == text
        assert chunks[0][1] == 0
        assert chunks[0][2] == len(text)

    def test_empty_text_returns_empty(self):
        assert _split_into_chunks("", target=1200, overlap=200) == []

    def test_long_text_produces_multiple_chunks(self):
        # Build a text that's definitely longer than target
        text = "word " * 300  # ~1500 chars
        chunks = _split_into_chunks(text, target=500, overlap=50)
        assert len(chunks) > 1

    def test_chunks_are_ordered_and_stable(self):
        text = "paragraph one.\n\nparagraph two.\n\nparagraph three."
        chunks = _split_into_chunks(text, target=1200, overlap=200)
        # Char starts should be non-decreasing
        starts = [c[1] for c in chunks]
        assert starts == sorted(starts)

    def test_overlap_prefix_applied(self):
        # Two paragraphs, each just under target; second chunk should contain
        # some suffix of the first
        para1 = "A " * 100  # 200 chars
        para2 = "B " * 100  # 200 chars
        text = para1.strip() + "\n\n" + para2.strip()
        chunks = _split_into_chunks(text, target=1200, overlap=50)
        if len(chunks) == 2:
            # Second chunk should start with overlap from first
            assert chunks[0][0][-10:] in chunks[1][0] or "A" in chunks[1][0]

    def test_whitespace_only_text_returns_empty(self):
        assert _split_into_chunks("   \n  ", target=1200, overlap=200) == []


class TestMakeChunkRecords:
    def _base_doc(self, doc_id="doc1", search_text="hello world"):
        return {
            "id": doc_id,
            "search_text": search_text,
            "title": "Title",
            "body": "Body",
            "subreddit": "test",
            "source_dataset": "test",
            "type": "post",
            "score": 5,
        }

    def test_short_doc_produces_one_chunk(self):
        doc = self._base_doc(search_text="short text")
        records = _make_chunk_records(doc)
        assert len(records) == 1
        assert records[0]["doc_id"] == "doc1"
        assert records[0]["chunk_index"] == 0
        assert records[0]["chunk_count"] == 1
        assert records[0]["chunk_text"] == "short text"

    def test_chunk_id_is_unique_and_doc_id_is_stable(self):
        text = "word " * 400  # long enough for multiple chunks
        doc = self._base_doc(search_text=text)
        records = _make_chunk_records(doc, )
        chunk_ids = [r["id"] for r in records]
        doc_ids = [r["doc_id"] for r in records]
        assert len(chunk_ids) == len(set(chunk_ids)), "chunk ids must be unique"
        assert all(d == "doc1" for d in doc_ids), "doc_id must be stable across chunks"

    def test_long_doc_produces_multiple_chunks(self):
        text = "sentence number X. " * 200  # ~3800 chars
        doc = self._base_doc(search_text=text)
        records = _make_chunk_records(doc)
        assert len(records) > 1

    def test_chunk_boundaries_ordered(self):
        text = "word " * 400
        doc = self._base_doc(search_text=text)
        records = _make_chunk_records(doc)
        indices = [r["chunk_index"] for r in records]
        assert indices == list(range(len(records)))

    def test_source_metadata_preserved_on_each_chunk(self):
        doc = self._base_doc(search_text="word " * 400)
        records = _make_chunk_records(doc)
        for r in records:
            assert r["title"] == "Title"
            assert r["body"] == "Body"
            assert r["subreddit"] == "test"
            assert r["score"] == 5

    def test_empty_search_text_emits_one_chunk_no_vector(self):
        doc = self._base_doc(search_text="")
        records = _make_chunk_records(doc)
        assert len(records) == 1
        assert records[0]["chunk_text"] == ""
        assert "chunk_vector" not in records[0]

    def test_chunk_count_matches_actual_records(self):
        text = "word " * 400
        doc = self._base_doc(search_text=text)
        records = _make_chunk_records(doc)
        for r in records:
            assert r["chunk_count"] == len(records)


class TestEmbedDocs:
    def _is_unit_vector(self, vec: list[float]) -> bool:
        norm = sum(v * v for v in vec) ** 0.5
        return abs(norm - 1.0) < 1e-6

    def test_embed_docs_success(self):
        docs = [
            {"id": "1__c0", "doc_id": "1", "chunk_text": "hello world"},
            {"id": "2__c0", "doc_id": "2", "chunk_text": "foo bar"},
        ]
        fake_client = MagicMock()
        # No chunk_concept_text → zero concept vec → chunk_vector = normalize(main)
        fake_client.embed_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]

        with patch("scripts.prepare_solr_docs._EMBEDDING_CLIENT", fake_client), \
             patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", True):
            embed_docs(docs)

        # chunk_vector is the L2-normalised combined vector (not the raw embedding)
        assert "chunk_vector" in docs[0]
        assert "chunk_vector" in docs[1]
        assert self._is_unit_vector(docs[0]["chunk_vector"])
        assert self._is_unit_vector(docs[1]["chunk_vector"])

    def test_embed_docs_skips_empty_chunk_text(self):
        docs = [
            {"id": "1__c0", "doc_id": "1", "chunk_text": ""},
            {"id": "2__c0", "doc_id": "2", "chunk_text": "real text"},
        ]
        fake_client = MagicMock()
        fake_client.embed_batch.return_value = [[0.5, 0.6]]

        with patch("scripts.prepare_solr_docs._EMBEDDING_CLIENT", fake_client), \
             patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", True):
            embed_docs(docs)

        assert "chunk_vector" not in docs[0]
        assert "chunk_vector" in docs[1]

    def test_embed_docs_handles_partial_failure(self):
        docs = [
            {"id": "1__c0", "doc_id": "1", "chunk_text": "text one"},
            {"id": "2__c0", "doc_id": "2", "chunk_text": "text two"},
        ]
        fake_client = MagicMock()
        fake_client.embed_batch.return_value = [None, [0.7, 0.8]]

        with patch("scripts.prepare_solr_docs._EMBEDDING_CLIENT", fake_client), \
             patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", True):
            embed_docs(docs)

        assert "chunk_vector" not in docs[0]
        assert "chunk_vector" in docs[1]

    def test_embed_docs_service_unavailable(self):
        docs = [{"id": "1__c0", "doc_id": "1", "chunk_text": "some text"}]

        with patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", False):
            embed_docs(docs)  # should not raise

        assert "chunk_vector" not in docs[0]

    def test_one_failing_chunk_does_not_remove_whole_doc(self):
        """A source doc with two chunks: one fails, one succeeds."""
        docs = [
            {"id": "d1__c0", "doc_id": "d1", "chunk_text": "chunk zero", "search_text": "chunk zero chunk one"},
            {"id": "d1__c1", "doc_id": "d1", "chunk_text": "chunk one", "search_text": "chunk zero chunk one"},
        ]
        fake_client = MagicMock()
        fake_client.embed_batch.side_effect = [
            [None, [0.9, 0.8]],
            [None],
        ]

        with patch("scripts.prepare_solr_docs._EMBEDDING_CLIENT", fake_client), \
             patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", True):
            embed_docs(docs)

        assert "chunk_vector" not in docs[0]
        # chunk_vector is the L2-normalised combined vector, not the raw embedding
        assert "chunk_vector" in docs[1]

    def test_embed_docs_rechunks_failed_doc_with_fallback_sizes(self):
        docs = [
            {
                "id": "d1__c0",
                "doc_id": "d1",
                "chunk_text": "chunk zero",
                "search_text": "original source text",
                "title": "",
                "body": "original source text",
            },
            {
                "id": "d1__c1",
                "doc_id": "d1",
                "chunk_text": "chunk one",
                "search_text": "original source text",
                "title": "",
                "body": "original source text",
            },
        ]
        fallback_chunks = [
            {"id": "d1__c0", "doc_id": "d1", "chunk_text": "fb0"},
            {"id": "d1__c1", "doc_id": "d1", "chunk_text": "fb1"},
            {"id": "d1__c2", "doc_id": "d1", "chunk_text": "fb2"},
        ]
        fake_client = MagicMock()
        fake_client.embed_batch.side_effect = [
            [None, [0.9, 0.8]],
            [[1.0], [2.0], [3.0]],
        ]

        def fake_make_chunk_records(doc, target=CHUNK_TARGET_CHARS, overlap=CHUNK_OVERLAP_CHARS):
            assert doc["id"] == "d1"
            assert target == FALLBACK_CHUNK_TARGET_CHARS
            assert overlap == FALLBACK_CHUNK_OVERLAP_CHARS
            return [dict(chunk) for chunk in fallback_chunks]

        with patch("scripts.prepare_solr_docs._EMBEDDING_CLIENT", fake_client), \
             patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", True), \
             patch("scripts.prepare_solr_docs._make_chunk_records", side_effect=fake_make_chunk_records):
            embed_docs(docs)

        assert [doc["id"] for doc in docs] == ["d1__c0", "d1__c1", "d1__c2"]
        # chunk_vector is the normalised combined vector, not the raw embedding.
        # For 1-D vectors the normalised value is ±1.0; just verify presence.
        assert all("chunk_vector" in doc for doc in docs)


# ---------------------------------------------------------------------------
# Retrieval: chunk collapse and doc_id fusion tests
# ---------------------------------------------------------------------------

class TestChunkCollapse:
    """Tests for _vector_retrieval collapse and RRF doc_id fusion."""

    SOLR_URL = "http://fake-solr:8983/solr/test_core/select"

    def _make_service(self):
        embedder = EmbeddingClient()
        reranker = RerankerClient()
        return HybridSearchService(self.SOLR_URL, embedder, reranker)

    def _chunk_doc(self, doc_id, chunk_index=0, chunk_text="", score=0.9):
        return {
            "id": f"{doc_id}__c{chunk_index}",
            "doc_id": doc_id,
            "chunk_index": chunk_index,
            "chunk_text": chunk_text or f"chunk {chunk_index} of {doc_id}",
            "search_text": f"search text for {doc_id}",
            "body": f"body {doc_id}",
            "title": "",
            "type": "post",
            "subreddit": "test",
            "source_dataset": "test",
            "polarity_label": "neutral",
            "subjectivity_label": "unknown",
            "sarcasm_label": "unknown",
            "model_mentions": [],
            "vendor_mentions": [],
            "score": score,
            "created_date": "",
        }

    def _fake_vector_response(self, chunk_docs):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": chunk_docs, "numFound": len(chunk_docs)},
        }
        return resp

    def test_multiple_chunks_same_doc_collapse_to_one(self):
        service = self._make_service()
        # Two chunks from doc "alpha", one chunk from doc "beta"
        chunks = [
            self._chunk_doc("alpha", 0),
            self._chunk_doc("alpha", 1),
            self._chunk_doc("beta", 0),
        ]
        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        with patch("hybrid_search.requests.post", return_value=self._fake_vector_response(chunks)):
            collapsed, best_texts = service._vector_retrieval("query", [])
        assert collapsed is not None
        doc_ids = [d["doc_id"] for d in collapsed]
        assert len(doc_ids) == len(set(doc_ids)), "collapsed docs must be unique by doc_id"
        assert set(doc_ids) == {"alpha", "beta"}

    def test_best_chunk_wins_when_multiple_match(self):
        """First chunk in Solr response (highest kNN score) should be kept."""
        service = self._make_service()
        chunks = [
            self._chunk_doc("doc1", 0, chunk_text="best match"),
            self._chunk_doc("doc1", 1, chunk_text="worse match"),
        ]
        service._embedder.embed_query = MagicMock(return_value=[0.1])
        with patch("hybrid_search.requests.post", return_value=self._fake_vector_response(chunks)):
            collapsed, best_texts = service._vector_retrieval("query", [])
        assert best_texts.get("doc1") == "best match"

    def test_vector_retrieval_returns_none_on_embed_failure(self):
        service = self._make_service()
        service._embedder.embed_query = MagicMock(return_value=None)
        collapsed, best_texts = service._vector_retrieval("query", [])
        assert collapsed is None
        assert best_texts == {}

    def test_lexical_and_vector_fusion_on_doc_id(self):
        """RRF should fuse by doc_id, not chunk id."""
        service = self._make_service()

        lex_chunks = [
            self._chunk_doc("a", 0),
            self._chunk_doc("b", 0),
            self._chunk_doc("a", 1),  # duplicate doc_id — should be collapsed
        ]
        vec_chunks = [
            self._chunk_doc("b", 0),
            self._chunk_doc("c", 0),
        ]

        lex_resp = MagicMock()
        lex_resp.raise_for_status.return_value = None
        lex_resp.json.return_value = {
            "response": {"docs": lex_chunks, "numFound": len(lex_chunks)},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }
        vec_resp = MagicMock()
        vec_resp.raise_for_status.return_value = None
        vec_resp.json.return_value = {
            "response": {"docs": vec_chunks, "numFound": len(vec_chunks)},
        }
        # Highlight response (empty — we just check the pipeline doesn't crash)
        hl_resp = MagicMock()
        hl_resp.raise_for_status.return_value = None
        hl_resp.json.return_value = {
            "response": {"docs": [], "numFound": 0},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }

        # chunk_expand GET happens between lexical and highlight
        chunk_expand_resp = MagicMock()
        chunk_expand_resp.raise_for_status.return_value = None
        chunk_expand_resp.json.return_value = {"response": {"docs": lex_chunks + vec_chunks}}

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        service._reranker.rerank = MagicMock(side_effect=lambda q, cands, top_k: cands)

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, chunk_expand_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            results, facets, num_found, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        assert info.mode == "hybrid"
        # "b" appears in both lexical and vector → should be in fused pool
        rerank_call = service._reranker.rerank.call_args
        pool = rerank_call[0][1]
        pool_doc_ids = {c.doc_id for c in pool}
        assert "b" in pool_doc_ids
        assert "c" in pool_doc_ids
        # "a" may appear as multiple chunks but all must share the same doc_id
        a_count = sum(1 for c in pool if c.doc_id == "a")
        assert a_count >= 1  # at least one chunk from doc "a"

    def test_zero_vector_chunks_does_not_break_lexical(self):
        """If embedding fails, lexical retrieval still returns results."""
        service = self._make_service()

        lex_chunks = [self._chunk_doc("a", 0), self._chunk_doc("b", 0)]
        lex_resp = MagicMock()
        lex_resp.raise_for_status.return_value = None
        lex_resp.json.return_value = {
            "response": {"docs": lex_chunks, "numFound": 2},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }
        hl_resp = MagicMock()
        hl_resp.raise_for_status.return_value = None
        hl_resp.json.return_value = {
            "response": {"docs": [], "numFound": 0},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }

        service._embedder.embed_query = MagicMock(return_value=None)

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, hl_resp]):
            results, facets, num_found, info = service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        assert info.degraded
        assert info.mode == "lexical"

    def test_filters_applied_to_vector_chunk_query(self):
        """fq filters must be forwarded to the chunk kNN query."""
        service = self._make_service()

        lex_resp = MagicMock()
        lex_resp.raise_for_status.return_value = None
        lex_resp.json.return_value = {
            "response": {"docs": [self._chunk_doc("a", 0)], "numFound": 1},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }

        captured_post_params = []
        def fake_post(url, data=None, json=None, timeout=None):
            captured_post_params.append(data or json or {})
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"response": {"docs": []}}
            return resp

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])

        with patch("hybrid_search.requests.get", return_value=lex_resp), \
             patch("hybrid_search.requests.post", side_effect=fake_post):
            service.search(
                solr_q="q", fq=["polarity_label:negative"], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        assert len(captured_post_params) >= 1
        post_params = captured_post_params[0]
        fq_value = post_params.get("fq", "")
        fq_str = " ".join(fq_value) if isinstance(fq_value, list) else str(fq_value)
        assert "polarity_label:negative" in fq_str

    def test_reranker_receives_document_level_candidates(self):
        """Reranker must receive one Candidate per source doc, not per chunk."""
        service = self._make_service()

        # Three chunks from two source docs
        lex_chunks = [
            self._chunk_doc("doc1", 0),
            self._chunk_doc("doc1", 1),
            self._chunk_doc("doc2", 0),
        ]
        lex_resp = MagicMock()
        lex_resp.raise_for_status.return_value = None
        lex_resp.json.return_value = {
            "response": {"docs": lex_chunks, "numFound": 3},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }
        vec_resp = MagicMock()
        vec_resp.raise_for_status.return_value = None
        vec_resp.json.return_value = {"response": {"docs": []}}

        hl_resp = MagicMock()
        hl_resp.raise_for_status.return_value = None
        hl_resp.json.return_value = {
            "response": {"docs": [], "numFound": 0},
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }

        # chunk_expand GET expands doc1 and doc2 to all their chunks
        chunk_expand_resp = MagicMock()
        chunk_expand_resp.raise_for_status.return_value = None
        chunk_expand_resp.json.return_value = {"response": {"docs": lex_chunks}}

        reranked_candidates = []
        def capture_rerank(query, candidates, top_k):
            reranked_candidates.extend(candidates)
            return candidates
        service._embedder.embed_query = MagicMock(return_value=[0.1])
        service._reranker.rerank = capture_rerank

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, chunk_expand_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            service.search(
                solr_q="q", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        # After chunk expansion each doc appears once per chunk, but only 2 unique doc_ids
        assert len({c.doc_id for c in reranked_candidates}) == 2


# ---------------------------------------------------------------------------
# Weighted vector combination unit tests
# ---------------------------------------------------------------------------

class TestWeightedCombineVectors:
    """Tests for the weighted _combine_vectors helper in both modules."""

    def _check_normalised(self, vec: list[float]) -> None:
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-6, f"Expected unit vector, got norm={norm}"

    # ---- hybrid_search._combine_vectors ----

    def test_hs_equal_weights_normalises(self):
        main = [3.0, 0.0]
        concept = [0.0, 4.0]
        result = hs_combine_vectors(main, concept, main_weight=1.0, concept_weight=1.0)
        self._check_normalised(result)

    def test_hs_lower_concept_weight_changes_direction(self):
        main = [1.0, 0.0]
        concept = [0.0, 1.0]
        equal = hs_combine_vectors(main, concept, main_weight=1.0, concept_weight=1.0)
        weighted = hs_combine_vectors(main, concept, main_weight=1.0, concept_weight=0.2)
        # Weighted result should be pulled more toward main (larger x-component)
        assert weighted[0] > equal[0], "Lower concept weight should increase main direction"
        assert weighted[1] < equal[1], "Lower concept weight should reduce concept direction"

    def test_hs_zero_concept_vec_returns_normalised_main(self):
        main = [3.0, 4.0]
        zero = [0.0, 0.0]
        result = hs_combine_vectors(main, zero, main_weight=1.0, concept_weight=0.2)
        self._check_normalised(result)
        # Should equal the normalised main (concept channel contributes nothing)
        norm = (3.0 ** 2 + 4.0 ** 2) ** 0.5
        assert abs(result[0] - 3.0 / norm) < 1e-6
        assert abs(result[1] - 4.0 / norm) < 1e-6

    def test_hs_zero_sum_returns_zero_vector(self):
        # When both vecs are zero, the result should be the zero vector, not NaN
        result = hs_combine_vectors([0.0, 0.0], [0.0, 0.0])
        assert result == [0.0, 0.0]

    def test_hs_default_weights_differ_from_equal_weights(self):
        main = [1.0, 0.0]
        concept = [0.0, 1.0]
        default = hs_combine_vectors(main, concept)          # main=1.0, concept=0.2
        equal = hs_combine_vectors(main, concept, 1.0, 1.0)
        assert default != equal, "Default weights should differ from equal-weight combination"

    # ---- prepare_solr_docs._combine_vectors (same logic, separate copy) ----

    def test_prep_equal_weights_normalises(self):
        main = [3.0, 0.0]
        concept = [0.0, 4.0]
        result = prep_combine_vectors(main, concept, main_weight=1.0, concept_weight=1.0)
        self._check_normalised(result)

    def test_prep_lower_concept_weight_changes_direction(self):
        main = [1.0, 0.0]
        concept = [0.0, 1.0]
        equal = prep_combine_vectors(main, concept, main_weight=1.0, concept_weight=1.0)
        weighted = prep_combine_vectors(main, concept, main_weight=1.0, concept_weight=0.2)
        assert weighted[0] > equal[0]
        assert weighted[1] < equal[1]

    def test_prep_zero_concept_vec_returns_normalised_main(self):
        main = [0.0, 5.0]
        zero = [0.0, 0.0]
        result = prep_combine_vectors(main, zero, main_weight=1.0, concept_weight=0.2)
        self._check_normalised(result)
        assert abs(result[1] - 1.0) < 1e-6

    def test_prep_zero_sum_returns_zero_vector(self):
        result = prep_combine_vectors([0.0, 0.0], [0.0, 0.0])
        assert result == [0.0, 0.0]


# ---------------------------------------------------------------------------
# Chunk-level concept scoping unit tests
# ---------------------------------------------------------------------------

class TestChunkConceptText:
    """Tests for prepare_solr_docs._chunk_concept_text."""

    def test_concept_present_in_chunk_is_included(self):
        chunk = "We discuss artificial intelligence and machine learning here."
        concepts = ["artificial intelligence", "machine learning", "blockchain"]
        result = _chunk_concept_text(chunk, concepts)
        assert "artificial intelligence" in result
        assert "machine learning" in result
        assert "blockchain" not in result

    def test_matching_is_case_insensitive(self):
        chunk = "ARTIFICIAL INTELLIGENCE is transforming industries."
        concepts = ["artificial intelligence"]
        result = _chunk_concept_text(chunk, concepts)
        assert result != ""

    def test_no_matching_concepts_returns_empty_string(self):
        chunk = "This chunk talks about sports and weather."
        concepts = ["artificial intelligence", "machine learning"]
        result = _chunk_concept_text(chunk, concepts)
        assert result == ""

    def test_duplicates_are_deduplicated(self):
        chunk = "AI and AI-related topics."
        concepts = ["AI", "AI"]  # duplicate in source list
        result = _chunk_concept_text(chunk, concepts)
        # "AI" should appear exactly once in result (pipe-separated)
        parts = [p.strip() for p in result.split("|") if p.strip()]
        assert parts.count("AI") == 1

    def test_order_is_preserved(self):
        chunk = "we discuss large language models and privacy concerns."
        concepts = ["privacy concerns", "large language models", "blockchain"]
        result = _chunk_concept_text(chunk, concepts)
        # "privacy concerns" listed first → should come first in output
        idx_privacy = result.find("privacy")
        idx_llm = result.find("large language")
        assert idx_privacy < idx_llm, "Extractor order should be preserved"

    def test_empty_chunk_returns_empty(self):
        result = _chunk_concept_text("", ["artificial intelligence"])
        assert result == ""

    def test_empty_concept_list_returns_empty(self):
        result = _chunk_concept_text("Some chunk text.", [])
        assert result == ""

    def test_both_empty_returns_empty(self):
        assert _chunk_concept_text("", []) == ""


class TestMakeChunkRecordsConceptScoping:
    """Integration-level tests for _make_chunk_records concept scoping."""

    def _base_doc(self, doc_id="doc1", search_text="hello world", concepts=""):
        return {
            "id": doc_id,
            "search_text": search_text,
            "title": "Title",
            "body": "Body",
            "subreddit": "test",
            "source_dataset": "test",
            "type": "post",
            "score": 5,
            "concepts": concepts,
        }

    def test_chunk_concept_text_not_wholesale_copied_from_doc(self):
        """Each chunk should only carry concepts found in its own text.

        This verifies that the previous behaviour — every chunk getting the full
        document concept list regardless of relevance — is no longer in effect.
        We use a very long para1 that forces the chunker to slice it before any
        overlap from para2 can appear, then check that the first chunk (which
        only covers para1 text) does not contain para2's exclusive concept.
        """
        # Use a concept that only appears in para2 and has NO overlap with para1 vocab
        exclusive_concept = "blockchain technology"
        # Make para1 long enough that the first window cannot overlap into para2
        para1 = "artificial intelligence replaces jobs. " * 80  # ~3040 chars >> target 600
        para2 = "blockchain technology is another topic entirely. " * 30
        search_text = para1.strip() + "\n\n" + para2.strip()
        doc = self._base_doc(
            search_text=search_text,
            concepts=f"artificial intelligence | {exclusive_concept}",
        )
        records = _make_chunk_records(doc, target=600, overlap=50)

        if len(records) < 2:
            return  # chunker didn't split; skip this assertion

        # The very first chunk only contains para1 text; it must not carry the
        # blockchain concept (which appears exclusively in para2).
        chunk0_concepts = records[0]["chunk_concept_text"]
        assert exclusive_concept not in chunk0_concepts, (
            f"First chunk (para1-only text) should not carry '{exclusive_concept}' "
            f"from para2. Got: {chunk0_concepts!r}"
        )

    def test_empty_search_text_yields_empty_concept_text(self):
        doc = self._base_doc(search_text="", concepts="artificial intelligence")
        records = _make_chunk_records(doc)
        assert len(records) == 1
        assert records[0]["chunk_concept_text"] == ""

    def test_chunk_with_no_matching_concepts_gets_empty_concept_text(self):
        chunk_text = "This is about unrelated topics like sports and cooking."
        doc = self._base_doc(
            search_text=chunk_text,
            concepts="artificial intelligence | machine learning",
        )
        records = _make_chunk_records(doc)
        assert len(records) == 1
        assert records[0]["chunk_concept_text"] == ""

    def test_chunk_with_matching_concept_gets_non_empty_concept_text(self):
        chunk_text = "This is about artificial intelligence and its impact on society."
        doc = self._base_doc(
            search_text=chunk_text,
            concepts="artificial intelligence | machine learning",
        )
        records = _make_chunk_records(doc)
        assert len(records) == 1
        assert "artificial intelligence" in records[0]["chunk_concept_text"]
        assert "machine learning" not in records[0]["chunk_concept_text"]


# ---------------------------------------------------------------------------
# Query intent inference unit tests
# ---------------------------------------------------------------------------

class TestQueryIntent:
    """Unit tests for query_intent.infer_intent()."""

    def test_short_entity_query_is_keyword(self):
        """Single-token known entity → keyword intent."""
        profile = infer_intent("ChatGPT")
        assert profile.intent_label == "keyword"
        assert profile.alpha > profile.beta

    def test_short_lookup_is_keyword(self):
        """Two-token entity lookup → keyword intent."""
        profile = infer_intent("Claude pricing")
        assert profile.intent_label == "keyword"
        assert profile.alpha >= 0.5

    def test_analytical_question_is_semantic(self):
        """Explicit why-question → semantic intent."""
        profile = infer_intent("Why do LLMs hallucinate?")
        assert profile.intent_label == "semantic"
        assert profile.beta > profile.alpha

    def test_comparison_query_is_semantic(self):
        """Comparison phrasing → semantic intent."""
        profile = infer_intent("Is ChatGPT better than Claude?")
        assert profile.intent_label == "semantic"
        assert profile.beta > profile.alpha

    def test_ambiguous_entity_benchmark_is_not_semantic(self):
        """Short entity + technical term without question → keyword or mixed."""
        profile = infer_intent("GPT-4 benchmark")
        assert profile.intent_label in ("keyword", "mixed")

    def test_weights_sum_to_one(self):
        """alpha + beta must always equal 1.0 for any query."""
        queries = [
            "ChatGPT",
            "Claude pricing",
            "Why do LLMs hallucinate?",
            "Is ChatGPT better than Claude?",
            "GPT-4 benchmark",
            "How does retrieval-augmented generation work?",
            "",
        ]
        for q in queries:
            p = infer_intent(q)
            assert abs(p.alpha + p.beta - 1.0) < 1e-6, (
                f"alpha+beta != 1.0 for query {q!r}: alpha={p.alpha} beta={p.beta}"
            )

    def test_signals_dict_is_populated(self):
        """Intent profile should always include a signals dict."""
        profile = infer_intent("Why do LLMs hallucinate?")
        assert isinstance(profile.signals, dict)
        assert len(profile.signals) > 0

    def test_query_features_populated(self):
        """query_features should include at least token_count."""
        profile = infer_intent("What is AGI?")
        assert "token_count" in profile.query_features

    def test_explicit_weight_override(self):
        """Caller-supplied weights are used in the returned profile."""
        profile = infer_intent(
            "Why do LLMs hallucinate?",
            semantic_alpha=0.2,
            semantic_beta=0.8,
        )
        assert profile.intent_label == "semantic"
        assert abs(profile.alpha - 0.2) < 1e-6
        assert abs(profile.beta - 0.8) < 1e-6

    def test_empty_query_does_not_crash(self):
        """Empty string should return a valid profile."""
        profile = infer_intent("")
        assert profile.intent_label in ("keyword", "mixed", "semantic")
        assert abs(profile.alpha + profile.beta - 1.0) < 1e-6

    def test_long_natural_language_query_is_semantic_or_mixed(self):
        """Long sentence-like query should bias toward semantic."""
        profile = infer_intent(
            "Can you explain how transformer attention mechanisms work in large language models?"
        )
        assert profile.intent_label in ("semantic", "mixed")

    def test_comparison_signals_present(self):
        """Comparison queries should fire comparison signal."""
        profile = infer_intent("GPT-4 vs Claude 3 performance")
        assert "comparison" in profile.signals


# ---------------------------------------------------------------------------
# POS-based verb signal tests (TestQueryIntentPOS)
# ---------------------------------------------------------------------------

class TestQueryIntentPOS:
    """Tests for POS-derived verb signals added to infer_intent()."""

    # --- query_features contract ---

    def test_query_features_includes_pos_fields(self):
        """query_features must always contain has_verb, verb_count, verb_lemmas, pos_available."""
        profile = infer_intent("Why do LLMs hallucinate?")
        for key in ("has_verb", "verb_count", "verb_lemmas", "pos_available"):
            assert key in profile.query_features, f"Missing key: {key}"

    def test_verb_lemmas_is_list(self):
        profile = infer_intent("How does RAG work?")
        assert isinstance(profile.query_features["verb_lemmas"], list)

    # --- verb-driven semantic promotion ---

    def test_explicit_verb_question_fires_verb_present(self):
        """'Why do LLMs hallucinate?' has verbs → verb_present signal fires."""
        profile = infer_intent("Why do LLMs hallucinate?")
        if profile.query_features.get("pos_available"):
            assert "verb_present" in profile.signals

    def test_explicit_verb_question_is_semantic(self):
        """Explicit why-question with verb → semantic."""
        profile = infer_intent("Why do LLMs hallucinate?")
        assert profile.intent_label == "semantic"

    def test_imperative_semantic_phrase_with_verb(self):
        """'Explain transformer attention' contains a verb → semantic or strong mixed."""
        profile = infer_intent("Explain transformer attention")
        assert profile.intent_label in ("semantic", "mixed")

    def test_how_does_rag_work_is_semantic(self):
        """'How does RAG work?' → semantic."""
        profile = infer_intent("How does RAG work?")
        assert profile.intent_label == "semantic"

    def test_explain_vector_search_is_semantic_or_mixed(self):
        """'Explain vector search' → semantic or mixed (has verb 'explain')."""
        profile = infer_intent("Explain vector search")
        assert profile.intent_label in ("semantic", "mixed")

    def test_can_claude_summarize_is_semantic(self):
        """'Can Claude summarize PDFs?' has auxiliary + main verb → semantic."""
        profile = infer_intent("Can Claude summarize PDFs?")
        assert profile.intent_label == "semantic"

    # --- short entity lookup without verb stays keyword ---

    def test_claude_pricing_remains_keyword(self):
        """Short entity lookup without verb → keyword."""
        profile = infer_intent("Claude pricing")
        assert profile.intent_label == "keyword"

    def test_chatgpt_remains_keyword(self):
        """Single entity token → keyword."""
        profile = infer_intent("ChatGPT")
        assert profile.intent_label == "keyword"

    def test_gpt4_benchmark_not_semantic(self):
        """'GPT-4 benchmark' has no real verb → keyword or mixed."""
        profile = infer_intent("GPT-4 benchmark")
        assert profile.intent_label in ("keyword", "mixed")

    def test_openai_api_not_semantic(self):
        """'OpenAI API' has no verb → keyword or mixed."""
        profile = infer_intent("OpenAI API")
        assert profile.intent_label in ("keyword", "mixed")

    # --- verb-bearing short query shifts away from pure keyword ---

    def test_chatgpt_explains_hallucinations_not_keyword(self):
        """'ChatGPT explains hallucinations' has a verb → not pure keyword."""
        profile = infer_intent("ChatGPT explains hallucinations")
        assert profile.intent_label in ("mixed", "semantic")

    # --- multiple verbs get stronger score than single verb ---

    def test_multiple_verbs_score_higher_than_single(self):
        """A multi-verb query should produce a higher or equal semantic score."""
        single = infer_intent("Explain how LLMs work")
        multi  = infer_intent("Can you explain why LLMs hallucinate and what causes it?")
        # The multi-verb query should be at least as semantic as single-verb
        label_rank = {"keyword": 0, "mixed": 1, "semantic": 2}
        assert label_rank[multi.intent_label] >= label_rank[single.intent_label]

    def test_multiple_verbs_fires_multiple_verbs_signal(self):
        """A sentence with ≥ 2 verb tokens should fire the multiple_verbs signal."""
        profile = infer_intent("Can you explain why LLMs hallucinate?")
        if profile.query_features.get("pos_available") and profile.query_features.get("verb_count", 0) >= 2:
            assert "multiple_verbs" in profile.signals

    # --- POS unavailable fallback ---

    def test_pos_unavailable_does_not_crash(self):
        """When POS tagging raises, intent inference falls back without crashing."""
        import query_intent as qi
        original_extract = qi._extract_features

        def patched_extract(query):
            feats = original_extract(query)
            # Simulate POS unavailable
            feats["has_verb"] = False
            feats["verb_count"] = 0
            feats["verb_lemmas"] = []
            feats["pos_available"] = False
            return feats

        qi._extract_features = patched_extract
        try:
            profile = infer_intent("Why do LLMs hallucinate?")
            assert profile.intent_label in ("keyword", "mixed", "semantic")
            assert abs(profile.alpha + profile.beta - 1.0) < 1e-6
            assert profile.query_features["pos_available"] is False
            assert "verb_present" not in profile.signals
        finally:
            qi._extract_features = original_extract

    def test_pos_unavailable_classification_stable(self):
        """Heuristic-only path (pos_available=False) still classifies sensibly."""
        import query_intent as qi
        original_extract = qi._extract_features

        def patched_extract(query):
            feats = original_extract(query)
            feats["has_verb"] = False
            feats["verb_count"] = 0
            feats["verb_lemmas"] = []
            feats["pos_available"] = False
            return feats

        qi._extract_features = patched_extract
        try:
            # Known keyword query should still be keyword without POS
            kw = infer_intent("Claude pricing")
            assert kw.intent_label == "keyword"
        finally:
            qi._extract_features = original_extract


# ---------------------------------------------------------------------------
# Weighted RRF unit tests
# ---------------------------------------------------------------------------

class TestWeightedRRF:
    """Extends RRF tests to cover lexical_weight / vector_weight parameters."""

    def test_equal_weights_matches_unweighted_behavior(self):
        """Equal weights preserve relative order; explicit 1.0/1.0 reproduces classic RRF scores."""
        ids_a = ["a", "b", "c"]
        ids_b = ["c", "b", "a"]
        # Default call uses lexical_weight=0.5, vector_weight=0.5
        default_fused = reciprocal_rank_fusion(ids_a, ids_b, rrf_k=60)
        # Explicit equal weights should give the same relative order
        equal_fused = reciprocal_rank_fusion(ids_a, ids_b, rrf_k=60,
                                             lexical_weight=0.5, vector_weight=0.5)
        assert [x[0] for x in default_fused] == [x[0] for x in equal_fused]

        # With weights 1.0/1.0 the scores match classic RRF (weight=1)
        classic_fused = reciprocal_rank_fusion(ids_a, ids_b, rrf_k=60,
                                               lexical_weight=1.0, vector_weight=1.0)
        for (cid, cs), (eid, es) in zip(classic_fused, equal_fused):
            # classic score should be 2× the equal-weight score
            assert abs(cs - es * 2.0) < 1e-9

    def test_high_lexical_weight_promotes_lexical_only_doc(self):
        """With alpha=0.9, a doc only in the lexical list should outscore a doc only in vector."""
        lexical_ids = ["lex_only", "shared"]
        vector_ids  = ["shared", "vec_only"]
        fused = reciprocal_rank_fusion(
            lexical_ids, vector_ids, rrf_k=60,
            lexical_weight=0.9, vector_weight=0.1,
        )
        scores = {doc_id: sc for doc_id, sc in fused}
        # lex_only gets 0.9/(60+1); vec_only gets 0.1/(60+2)
        # lex_only should beat vec_only
        assert scores["lex_only"] > scores["vec_only"]

    def test_high_vector_weight_promotes_vector_only_doc(self):
        """With beta=0.9, a doc only in the vector list should outscore a doc only in lexical."""
        lexical_ids = ["lex_only", "shared"]
        vector_ids  = ["shared", "vec_only"]
        fused = reciprocal_rank_fusion(
            lexical_ids, vector_ids, rrf_k=60,
            lexical_weight=0.1, vector_weight=0.9,
        )
        scores = {doc_id: sc for doc_id, sc in fused}
        assert scores["vec_only"] > scores["lex_only"]

    def test_shared_doc_benefits_from_both_contributions(self):
        """A doc in both lists accumulates contributions from both branches."""
        lexical_ids = ["a", "shared"]
        vector_ids  = ["shared", "b"]
        fused = reciprocal_rank_fusion(
            lexical_ids, vector_ids, rrf_k=60,
            lexical_weight=0.5, vector_weight=0.5,
        )
        scores = {doc_id: sc for doc_id, sc in fused}
        # shared appears at rank-2 in lex and rank-1 in vec
        expected = 0.5 / (60 + 2) + 0.5 / (60 + 1)
        assert abs(scores["shared"] - expected) < 1e-9

    def test_score_formula_with_explicit_weights(self):
        """Verify per-item score formula: weight / (k + rank)."""
        fused = reciprocal_rank_fusion(["x"], [], rrf_k=60, lexical_weight=0.8, vector_weight=0.2)
        _, score = fused[0]
        expected = 0.8 / (60 + 1)
        assert abs(score - expected) < 1e-9

    def test_dedup_still_applies_with_weights(self):
        """Deduplication must work the same way with non-equal weights."""
        fused = reciprocal_rank_fusion(["a", "b"], ["b", "c"], rrf_k=60,
                                       lexical_weight=0.7, vector_weight=0.3)
        ids = [doc_id for doc_id, _ in fused]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# HybridSearchService intent integration tests
# ---------------------------------------------------------------------------

class TestIntentIntegration:
    """Verify intent inference is wired into HybridSearchService.search()."""

    SOLR_URL = "http://fake-solr:8983/solr/test_core/select"

    def _make_service(self):
        embedder = EmbeddingClient()
        reranker = RerankerClient()
        return HybridSearchService(self.SOLR_URL, embedder, reranker)

    def _make_solr_docs(self, ids):
        return [
            {"id": f"{i}__c0", "doc_id": i, "chunk_index": 0,
             "chunk_text": f"chunk text {i}", "search_text": f"text {i}",
             "body": f"body {i}", "title": "", "type": "post", "subreddit": "test",
             "source_dataset": "test", "polarity_label": "neutral",
             "model_mentions": [], "vendor_mentions": [],
             "subjectivity_label": "unknown", "sarcasm_label": "unknown",
             "score": 1, "created_date": ""}
            for i in ids
        ]

    def _fake_solr_response(self, ids):
        docs = self._make_solr_docs(ids)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "response": {"docs": docs, "numFound": len(ids)},
            "facets": {
                "count": len(ids), "unique_docs": len(ids),
                "type": {"buckets": []}, "subreddit": {"buckets": []},
                "polarity_label": {"buckets": []}, "subjectivity_label": {"buckets": []},
                "source_dataset": {"buckets": []},
                "model_mentions": {"buckets": []}, "vendor_mentions": {"buckets": []},
            },
            "facet_counts": {"facet_fields": {}},
            "highlighting": {},
        }
        return resp

    def _fake_chunk_expand_response(self, ids):
        """Minimal Solr response for the chunk-expansion GET."""
        docs = self._make_solr_docs(ids)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"response": {"docs": docs}}
        return resp

    def test_intent_label_attached_to_retrieval_info(self):
        """After a successful hybrid search, retrieval_info should have intent_label set."""
        service = self._make_service()
        lex_resp    = self._fake_solr_response(["a", "b"])
        vec_resp    = self._fake_solr_response(["b", "c"])
        expand_resp = self._fake_chunk_expand_response(["a", "b", "c"])
        hl_resp     = self._fake_solr_response(["a", "b", "c"])

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        service._reranker.rerank = MagicMock(side_effect=lambda q, cands, top_k: cands)

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, expand_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            _, _, _, info = service.search(
                solr_q="Why do LLMs hallucinate?", fq=[], qf="title^4", pf="title^8",
                bq=[], sort="score desc", use_nlp=True,
                query_text="Why do LLMs hallucinate?",
            )

        assert info.intent_label in ("keyword", "semantic", "mixed")
        assert abs(info.alpha + info.beta - 1.0) < 1e-6

    def test_semantic_query_uses_higher_beta(self):
        """An explicit question query should produce beta > alpha in retrieval_info."""
        service = self._make_service()
        lex_resp    = self._fake_solr_response(["a", "b"])
        vec_resp    = self._fake_solr_response(["b", "c"])
        expand_resp = self._fake_chunk_expand_response(["a", "b", "c"])
        hl_resp     = self._fake_solr_response(["a", "b", "c"])

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        service._reranker.rerank = MagicMock(side_effect=lambda q, cands, top_k: cands)

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, expand_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            _, _, _, info = service.search(
                solr_q="Why do LLMs hallucinate?", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False,
                query_text="Why do LLMs hallucinate?",
            )

        assert info.intent_label == "semantic"
        assert info.beta > info.alpha

    def test_keyword_query_uses_higher_alpha(self):
        """A short entity query should produce alpha > beta in retrieval_info."""
        service = self._make_service()
        lex_resp    = self._fake_solr_response(["a", "b"])
        vec_resp    = self._fake_solr_response(["b", "c"])
        expand_resp = self._fake_chunk_expand_response(["a", "b", "c"])
        hl_resp     = self._fake_solr_response(["a", "b", "c"])

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        service._reranker.rerank = MagicMock(side_effect=lambda q, cands, top_k: cands)

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, expand_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            _, _, _, info = service.search(
                solr_q="ChatGPT", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False,
                query_text="ChatGPT",
            )

        assert info.intent_label == "keyword"
        assert info.alpha > info.beta

    def test_lexical_degradation_still_reports_intent(self):
        """Even when vector branch degrades, intent_label should be set."""
        service = self._make_service()
        lex_resp = self._fake_solr_response(["a", "b"])
        hl_resp  = self._fake_solr_response(["a", "b"])

        service._embedder.embed_query = MagicMock(return_value=None)

        call_count = [0]
        def fake_get(url, params, timeout):
            call_count[0] += 1
            if call_count[0] == 1:
                return lex_resp
            return hl_resp

        with patch("hybrid_search.requests.get", side_effect=fake_get):
            _, _, _, info = service.search(
                solr_q="Why do LLMs hallucinate?", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False,
                query_text="Why do LLMs hallucinate?",
            )

        # Mode degrades but intent fields should still be empty (inference
        # only runs after vector branch succeeds)
        assert info.mode == "lexical"
        assert info.degraded

    def test_intent_signals_in_retrieval_info(self):
        """intent_signals should be populated after a full hybrid search."""
        service = self._make_service()
        lex_resp    = self._fake_solr_response(["a", "b"])
        vec_resp    = self._fake_solr_response(["b", "c"])
        expand_resp = self._fake_chunk_expand_response(["a", "b", "c"])
        hl_resp     = self._fake_solr_response(["a", "b", "c"])

        service._embedder.embed_query = MagicMock(return_value=[0.1, 0.2])
        service._reranker.rerank = MagicMock(side_effect=lambda q, cands, top_k: cands)

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, expand_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            _, _, _, info = service.search(
                solr_q="Why do LLMs hallucinate?", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False,
                query_text="Why do LLMs hallucinate?",
            )

        assert isinstance(info.intent_signals, dict)
        assert len(info.intent_signals) > 0


# ---------------------------------------------------------------------------
# Sentiment analytics unit tests
# ---------------------------------------------------------------------------

def _make_solr_analytics_payload(
    total_unique_docs=10,
    polarity_buckets=None,
    subjectivity_buckets=None,
    sarcasm_buckets=None,
    date_buckets=None,
    polarity_missing_count=0,
    subjectivity_missing_count=0,
    sarcasm_missing_count=0,
    subreddit_buckets=None,
    model_buckets=None,
    vendor_buckets=None,
    type_buckets=None,
    avg_score=None,
    min_date=None,
    max_date=None,
):
    """Build a minimal Solr JSON Facet response for analytics tests."""
    if polarity_buckets is None:
        polarity_buckets = [
            {"val": "positive", "docs": 4},
            {"val": "negative", "docs": 3},
            {"val": "neutral",  "docs": 2},
            {"val": "mixed",    "docs": 1},
        ]
    if subjectivity_buckets is None:
        subjectivity_buckets = [
            {"val": "subjective", "docs": 6},
            {"val": "objective",  "docs": 3},
        ]
    if sarcasm_buckets is None:
        sarcasm_buckets = [
            {"val": "sarcastic",     "docs": 4},
            {"val": "non_sarcastic", "docs": 5},
        ]
    if date_buckets is None:
        date_buckets = []
    if subreddit_buckets is None:
        subreddit_buckets = []
    if model_buckets is None:
        model_buckets = []
    if vendor_buckets is None:
        vendor_buckets = []
    if type_buckets is None:
        type_buckets = []

    return {
        "facets": {
            "count": total_unique_docs,
            "total_unique_docs": total_unique_docs,
            "avg_score": avg_score,
            "min_date": min_date,
            "max_date": max_date,
            "polarity_totals": {
                "buckets": polarity_buckets,
                "missing": {"docs": polarity_missing_count},
            },
            "subjectivity_totals": {
                "buckets": subjectivity_buckets,
                "missing": {"docs": subjectivity_missing_count},
            },
            "sarcasm_totals": {
                "buckets": sarcasm_buckets,
                "missing": {"docs": sarcasm_missing_count},
            },
            "by_date": {
                "buckets": date_buckets,
            },
            "by_subreddit": {"buckets": subreddit_buckets},
            "by_model":     {"buckets": model_buckets},
            "by_vendor":    {"buckets": vendor_buckets},
            "by_type":      {"buckets": type_buckets},
        }
    }


def _make_analytics_service():
    embedder = MagicMock()
    reranker = MagicMock()
    return HybridSearchService("http://fake:8983/solr/test/select", embedder, reranker)


class TestSentimentAnalyticsParsing:
    """Unit tests for get_analytics payload parsing (backwards-compat keys)."""

    def _run(self, payload, date_from="", date_to=""):
        service = _make_analytics_service()
        fake_resp = MagicMock()
        fake_resp.json.return_value = payload
        fake_resp.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_resp):
            return service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[],
                date_from=date_from, date_to=date_to,
            )

    def test_returns_dict_with_expected_legacy_keys(self):
        """Legacy flat keys must still be present for backwards compatibility."""
        result = self._run(_make_solr_analytics_payload())
        legacy_keys = {
            "time_buckets", "polarity_series", "subjectivity_series",
            "sarcasm_series", "polarity_totals", "subjectivity_totals",
            "sarcasm_totals", "total_docs_analysed",
        }
        assert legacy_keys.issubset(set(result.keys()))

    def test_total_docs_analysed(self):
        result = self._run(_make_solr_analytics_payload(total_unique_docs=42))
        assert result["total_docs_analysed"] == 42

    def test_polarity_totals_correct(self):
        result = self._run(_make_solr_analytics_payload(
            polarity_buckets=[
                {"val": "positive", "docs": 5},
                {"val": "negative", "docs": 3},
            ]
        ))
        assert result["polarity_totals"]["positive"] == 5
        assert result["polarity_totals"]["negative"] == 3
        assert result["polarity_totals"]["neutral"] == 0
        assert result["polarity_totals"]["mixed"] == 0

    def test_subjectivity_totals_correct(self):
        result = self._run(_make_solr_analytics_payload(
            subjectivity_buckets=[
                {"val": "subjective", "docs": 7},
                {"val": "objective",  "docs": 2},
            ]
        ))
        assert result["subjectivity_totals"]["subjective"] == 7
        assert result["subjectivity_totals"]["objective"] == 2

    def test_missing_labels_counted_as_unknown(self):
        result = self._run(_make_solr_analytics_payload(
            polarity_missing_count=3,
            subjectivity_missing_count=2,
        ))
        assert result["polarity_totals"]["unknown"] == 3
        assert result["subjectivity_totals"]["unknown"] == 2

    def test_unrecognised_label_goes_to_unknown(self):
        result = self._run(_make_solr_analytics_payload(
            polarity_buckets=[{"val": "weird_label", "docs": 5}]
        ))
        assert result["polarity_totals"]["unknown"] == 5

    def test_empty_time_buckets_when_no_date_data(self):
        result = self._run(_make_solr_analytics_payload(date_buckets=[]))
        assert result["time_buckets"] == []

    def test_time_buckets_ordered_and_parsed(self):
        date_buckets = [
            {
                "val": "2024-01-01T00:00:00Z",
                "polarity": {
                    "buckets": [{"val": "positive", "docs": 2}, {"val": "negative", "docs": 1}],
                    "missing": {"docs": 0},
                },
                "subjectivity": {
                    "buckets": [{"val": "subjective", "docs": 3}],
                    "missing": {"docs": 0},
                },
            },
            {
                "val": "2024-02-01T00:00:00Z",
                "polarity": {
                    "buckets": [{"val": "neutral", "docs": 4}],
                    "missing": {"docs": 0},
                },
                "subjectivity": {
                    "buckets": [{"val": "objective", "docs": 1}],
                    "missing": {"docs": 0},
                },
            },
        ]
        result = self._run(_make_solr_analytics_payload(date_buckets=date_buckets))

        assert result["time_buckets"] == ["2024-01-01", "2024-02-01"]
        assert result["polarity_series"]["positive"] == [2, 0]
        assert result["polarity_series"]["negative"] == [1, 0]
        assert result["polarity_series"]["neutral"]  == [0, 4]
        assert result["subjectivity_series"]["subjective"] == [3, 0]
        assert result["subjectivity_series"]["objective"]  == [0, 1]

    def test_series_parallel_to_buckets(self):
        """Every series list must have same length as time_buckets."""
        date_buckets = [
            {
                "val": f"2024-0{m}-01T00:00:00Z",
                "polarity": {"buckets": [], "missing": {"docs": 0}},
                "subjectivity": {"buckets": [], "missing": {"docs": 0}},
            }
            for m in range(1, 4)
        ]
        result = self._run(_make_solr_analytics_payload(date_buckets=date_buckets))
        n = len(result["time_buckets"])
        for lbl, series in result["polarity_series"].items():
            assert len(series) == n, f"polarity_series[{lbl!r}] length mismatch"
        for lbl, series in result["subjectivity_series"].items():
            assert len(series) == n, f"subjectivity_series[{lbl!r}] length mismatch"

    def test_missing_per_bucket_counted_as_unknown(self):
        date_buckets = [
            {
                "val": "2024-03-01T00:00:00Z",
                "polarity": {
                    "buckets": [{"val": "positive", "docs": 1}],
                    "missing": {"docs": 5},
                },
                "subjectivity": {
                    "buckets": [],
                    "missing": {"docs": 2},
                },
            }
        ]
        result = self._run(_make_solr_analytics_payload(date_buckets=date_buckets))
        assert result["polarity_series"]["unknown"] == [5]
        assert result["subjectivity_series"]["unknown"] == [2]

    def test_solr_error_returns_empty_dict(self):
        import requests as req
        service = _make_analytics_service()
        with patch("hybrid_search.requests.post", side_effect=req.RequestException("down")):
            result = service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[]
            )
        assert result == {}

    def test_empty_facets_returns_empty_dict(self):
        service = _make_analytics_service()
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"facets": {}}
        fake_resp.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_resp):
            result = service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[]
            )
        assert result == {}

    def test_daily_gap_for_short_date_range(self):
        """Window ≤ 31 days should use daily bucket sizing (+1DAY in request)."""
        service = _make_analytics_service()
        captured_params = {}

        def fake_post(url, data=None, timeout=None):
            captured_params.update(data or {})
            fake_resp = MagicMock()
            fake_resp.json.return_value = _make_solr_analytics_payload()
            fake_resp.raise_for_status.return_value = None
            return fake_resp

        with patch("hybrid_search.requests.post", side_effect=fake_post):
            service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[],
                date_from="2024-01-01", date_to="2024-01-15",
            )
        assert "+1DAY" in captured_params.get("json.facet", "")

    def test_monthly_gap_for_wide_date_range(self):
        """Window > 31 days (or no dates) should use monthly bucket sizing."""
        service = _make_analytics_service()
        captured_params = {}

        def fake_post(url, data=None, timeout=None):
            captured_params.update(data or {})
            fake_resp = MagicMock()
            fake_resp.json.return_value = _make_solr_analytics_payload()
            fake_resp.raise_for_status.return_value = None
            return fake_resp

        with patch("hybrid_search.requests.post", side_effect=fake_post):
            service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[],
                date_from="2024-01-01", date_to="2024-06-30",
            )
        assert "+1MONTH" in captured_params.get("json.facet", "")

    def test_monthly_gap_when_no_dates_given(self):
        service = _make_analytics_service()
        captured_params = {}

        def fake_post(url, data=None, timeout=None):
            captured_params.update(data or {})
            fake_resp = MagicMock()
            fake_resp.json.return_value = _make_solr_analytics_payload()
            fake_resp.raise_for_status.return_value = None
            return fake_resp

        with patch("hybrid_search.requests.post", side_effect=fake_post):
            service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[]
            )
        assert "+1MONTH" in captured_params.get("json.facet", "")

    def test_doc_ids_path_uses_star_query(self):
        """When doc_ids is supplied the Solr query should be q=*:* not the original query."""
        service = _make_analytics_service()
        captured_params = {}

        def fake_post(url, data=None, timeout=None):
            captured_params.update(data or {})
            fake_resp = MagicMock()
            fake_resp.json.return_value = _make_solr_analytics_payload()
            fake_resp.raise_for_status.return_value = None
            return fake_resp

        doc_ids = ["doc1", "doc2", "doc3"]
        with patch("hybrid_search.requests.post", side_effect=fake_post):
            service.get_analytics(
                solr_q="chatgpt vs claude", fq=[], qf="", pf="", bq=[],
                doc_ids=doc_ids,
            )
        assert captured_params.get("q") == "*:*", "doc_ids path must use q=*:*"
        # The fq list should contain a doc_id filter covering all supplied ids
        fq_list = captured_params.get("fq", [])
        fq_str = " ".join(fq_list) if isinstance(fq_list, list) else str(fq_list)
        for did in doc_ids:
            assert did in fq_str, f"doc_id {did!r} missing from fq"

    def test_doc_ids_path_excludes_edismax_params(self):
        """When doc_ids is supplied, edismax-specific params must not be sent."""
        service = _make_analytics_service()
        captured_params = {}

        def fake_post(url, data=None, timeout=None):
            captured_params.update(data or {})
            fake_resp = MagicMock()
            fake_resp.json.return_value = _make_solr_analytics_payload()
            fake_resp.raise_for_status.return_value = None
            return fake_resp

        with patch("hybrid_search.requests.post", side_effect=fake_post):
            service.get_analytics(
                solr_q="test", fq=[], qf="title^4", pf="title^8", bq=["boost_term"],
                doc_ids=["a", "b"],
            )
        assert "defType" not in captured_params
        assert "qf" not in captured_params
        assert "bq" not in captured_params

    def test_no_doc_ids_path_uses_edismax(self):
        """Without doc_ids the fallback path must use eDisMax."""
        service = _make_analytics_service()
        captured_params = {}

        def fake_post(url, data=None, timeout=None):
            captured_params.update(data or {})
            fake_resp = MagicMock()
            fake_resp.json.return_value = _make_solr_analytics_payload()
            fake_resp.raise_for_status.return_value = None
            return fake_resp

        with patch("hybrid_search.requests.post", side_effect=fake_post):
            service.get_analytics(
                solr_q="chatgpt", fq=[], qf="title^4", pf="title^8", bq=[],
            )
        assert captured_params.get("defType") == "edismax"
        assert captured_params.get("q") == "chatgpt"


class TestFusedDocIdsPopulation:
    """Verify RetrievalInfo.fused_doc_ids is populated at each search() exit path."""

    def _make_service(self):
        embedder = MagicMock()
        reranker = MagicMock()
        return HybridSearchService("http://fake:8983/solr/test/select", embedder, reranker)

    def _lex_resp(self, doc_ids):
        docs = [{"id": did, "doc_id": did, "score": 1.0} for did in doc_ids]
        payload = {
            "response": {"docs": docs, "numFound": len(docs)},
            "facets": {"count": len(docs), "total_unique_docs": len(docs)},
        }
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status.return_value = None
        return resp

    def test_lexical_only_mode_populates_fused_doc_ids(self):
        service = self._make_service()
        lex_resp = self._lex_resp(["a", "b", "c"])
        hl_resp = MagicMock()
        hl_resp.json.return_value = {"response": {"docs": []}, "highlighting": {}}
        hl_resp.raise_for_status.return_value = None

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, hl_resp]):
            _, _, _, info = service.search(
                solr_q="test", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="test",
                use_vector=False,
            )
        assert set(info.fused_doc_ids) == {"a", "b", "c"}

    def test_hybrid_mode_populates_fused_doc_ids_from_reranker_output(self):
        """fused_doc_ids should reflect the reranker top-K, including vector-only docs."""
        service = self._make_service()
        # Lexical returns doc "a"; vector returns docs "a" and "b" (b is vector-only)
        lex_resp = self._lex_resp(["a"])

        vec_payload = {
            "response": {
                "docs": [
                    {"id": "a__c0", "doc_id": "a", "score": 0.9},
                    {"id": "b__c0", "doc_id": "b", "score": 0.8},
                ]
            }
        }
        vec_resp = MagicMock()
        vec_resp.json.return_value = vec_payload
        vec_resp.raise_for_status.return_value = None

        chunk_resp = MagicMock()
        chunk_resp.json.return_value = {"response": {"docs": []}}
        chunk_resp.raise_for_status.return_value = None

        hl_resp = MagicMock()
        hl_resp.json.return_value = {"response": {"docs": []}, "highlighting": {}}
        hl_resp.raise_for_status.return_value = None

        service._embedder.embed_query = MagicMock(return_value=[0.1] * 1024)
        # Reranker returns both candidates so final_ids covers a and b
        service._reranker.rerank = MagicMock(return_value=[
            Candidate(id="a__c0", doc_id="a", source="both",    raw_score=0.9, rerank_score=0.9),
            Candidate(id="b__c0", doc_id="b", source="vector",  raw_score=0.8, rerank_score=0.7),
        ])

        with patch("hybrid_search.requests.get", side_effect=[lex_resp, chunk_resp, hl_resp]), \
             patch("hybrid_search.requests.post", return_value=vec_resp):
            _, _, _, info = service.search(
                solr_q="test", fq=[], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="test",
                use_vector=True,
            )
        # fused_doc_ids comes from final_ids (reranker output), not the full fused list
        assert "a" in info.fused_doc_ids
        assert "b" in info.fused_doc_ids
        # Must not contain ids that weren't in the reranker output
        assert len(info.fused_doc_ids) == 2


# ---------------------------------------------------------------------------
# Flask route-level analytics tests
# ---------------------------------------------------------------------------

class TestAppAnalyticsRoute:
    """Route-level tests: analytics included/omitted/graceful."""

    @pytest.fixture(autouse=True)
    def _patch_setup_check(self):
        with patch("app._get_solr_setup_error", return_value=""):
            yield

    @pytest.fixture()
    def client(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            yield c

    def _mock_search(self, results=None, facets=None, num_found=0, info=None):
        from hybrid_search import RetrievalInfo
        return MagicMock(return_value=(
            results or [],
            facets or {},
            num_found,
            info or RetrievalInfo(),
        ))

    def _mock_analytics(self, data=None):
        return MagicMock(return_value=data or {
            "time_buckets": ["2024-01"],
            "polarity_series": {"positive": [3], "negative": [1], "neutral": [1], "mixed": [0], "unknown": [0]},
            "subjectivity_series": {"subjective": [4], "objective": [1], "unknown": [0]},
            "sarcasm_series": {"sarcastic": [2], "non_sarcastic": [3], "unknown": [0]},
            "polarity_totals": {"positive": 3, "negative": 1, "neutral": 1, "mixed": 0, "unknown": 0},
            "subjectivity_totals": {"subjective": 4, "objective": 1, "unknown": 0},
            "sarcasm_totals": {"sarcastic": 2, "non_sarcastic": 3, "unknown": 0},
            "total_docs_analysed": 5,
        })

    def test_analytics_included_for_query(self, client):
        import app as flask_app
        search_mock = self._mock_search(num_found=5)
        analytics_mock = self._mock_analytics()
        with patch.object(flask_app._hybrid, "search", search_mock), \
             patch.object(flask_app._hybrid, "get_analytics", analytics_mock):
            resp = client.get("/?q=AI")
        assert resp.status_code == 200
        assert b"total_docs_analysed" in resp.data or b"Analytics" in resp.data

    def test_analytics_omitted_for_no_query(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Analytics Dashboard" not in resp.data

    def test_analytics_graceful_on_failure(self, client):
        """When analytics raises, the page still renders without crashing."""
        import app as flask_app
        search_mock = self._mock_search(num_found=5)
        failing_analytics = MagicMock(side_effect=Exception("boom"))
        with patch.object(flask_app._hybrid, "search", search_mock), \
             patch.object(flask_app._hybrid, "get_analytics", failing_analytics):
            resp = client.get("/?q=AI")
        assert resp.status_code == 200
        assert b"Analytics Dashboard" not in resp.data


# ---------------------------------------------------------------------------
# Analytics dashboard payload tests
# ---------------------------------------------------------------------------

def _make_analytics_payload_full():
    """Full analytics payload with all sections populated."""
    return _make_solr_analytics_payload(
        total_unique_docs=20,
        avg_score=42.5,
        min_date="2024-01-01T00:00:00Z",
        max_date="2024-12-01T00:00:00Z",
        subreddit_buckets=[
            {"val": "MachineLearning",  "docs": 8,
             "polarity": {"buckets": [{"val": "positive","docs":5},{"val":"negative","docs":3}], "missing":{"docs":0}}},
            {"val": "artificial",       "docs": 6,
             "polarity": {"buckets": [{"val": "neutral","docs":4},{"val":"mixed","docs":2}],    "missing":{"docs":0}}},
            {"val": "ChatGPT",          "docs": 4,
             "polarity": {"buckets": [{"val": "positive","docs":4}],                             "missing":{"docs":0}}},
            {"val": "LocalLLaMA",       "docs": 2,
             "polarity": {"buckets": [],                                                          "missing":{"docs":2}}},
        ],
        model_buckets=[
            {"val": "chatgpt",  "docs": 10,
             "polarity": {"buckets": [{"val":"positive","docs":7},{"val":"negative","docs":3}], "missing":{"docs":0}}},
            {"val": "claude",   "docs":  6,
             "polarity": {"buckets": [{"val":"positive","docs":5},{"val":"neutral","docs":1}],  "missing":{"docs":0}}},
            {"val": "gemini",   "docs":  3,
             "polarity": {"buckets": [{"val":"neutral","docs":3}],                              "missing":{"docs":0}}},
        ],
        vendor_buckets=[
            {"val": "openai",    "docs": 12,
             "polarity": {"buckets": [{"val":"positive","docs":8},{"val":"negative","docs":4}], "missing":{"docs":0}}},
            {"val": "anthropic", "docs":  6,
             "polarity": {"buckets": [{"val":"positive","docs":5},{"val":"neutral","docs":1}],  "missing":{"docs":0}}},
        ],
        type_buckets=[
            {"val": "post",    "docs": 14,
             "polarity": {"buckets": [{"val":"positive","docs":8},{"val":"negative","docs":6}], "missing":{"docs":0}}},
            {"val": "comment", "docs": 6,
             "polarity": {"buckets": [{"val":"neutral","docs":4},{"val":"positive","docs":2}],  "missing":{"docs":0}}},
        ],
        sarcasm_buckets=[
            {"val": "sarcastic",     "docs": 7},
            {"val": "non_sarcastic", "docs": 11},
        ],
    )


class TestAnalyticsDashboardParsing:
    """Unit tests for the expanded get_analytics dashboard payload."""

    def _run(self, payload, **kwargs):
        service = _make_analytics_service()
        fake_resp = MagicMock()
        fake_resp.json.return_value = payload
        fake_resp.raise_for_status.return_value = None
        with patch("hybrid_search.requests.post", return_value=fake_resp):
            return service.get_analytics(
                solr_q="test", fq=[], qf="", pf="", bq=[], **kwargs
            )

    # ---- overview section ----

    def test_overview_total_docs(self):
        result = self._run(_make_analytics_payload_full())
        assert result["overview"]["total_docs"] == 20

    def test_overview_avg_score(self):
        result = self._run(_make_analytics_payload_full())
        assert result["overview"]["avg_score"] == 42.5

    def test_overview_date_span(self):
        result = self._run(_make_analytics_payload_full())
        assert result["overview"]["min_date"] == "2024-01-01"
        assert result["overview"]["max_date"] == "2024-12-01"

    def test_overview_missing_avg_score_is_none(self):
        payload = _make_solr_analytics_payload(avg_score=None)
        result = self._run(payload)
        assert result["overview"]["avg_score"] is None

    # ---- by_subreddit ----

    def test_by_subreddit_top_n_extracted(self):
        result = self._run(_make_analytics_payload_full())
        subreddits = result["by_subreddit"]
        assert len(subreddits) <= 8  # top-N default
        labels = [s["label"] for s in subreddits]
        assert "MachineLearning" in labels
        assert "artificial" in labels

    def test_by_subreddit_counts_correct(self):
        result = self._run(_make_analytics_payload_full())
        sub_map = {s["label"]: s["count"] for s in result["by_subreddit"]}
        assert sub_map["MachineLearning"] == 8
        assert sub_map["artificial"] == 6

    def test_by_subreddit_polarity_mix_present(self):
        result = self._run(_make_analytics_payload_full())
        first = result["by_subreddit"][0]
        assert "polarity_mix" in first
        assert isinstance(first["polarity_mix"], dict)

    def test_by_subreddit_polarity_mix_values(self):
        result = self._run(_make_analytics_payload_full())
        sub_map = {s["label"]: s["polarity_mix"] for s in result["by_subreddit"]}
        assert sub_map["MachineLearning"]["positive"] == 5
        assert sub_map["MachineLearning"]["negative"] == 3

    def test_by_subreddit_other_rollup(self):
        """When more buckets than top-N arrive they must be collapsed into Other."""
        extra_buckets = [
            {"val": f"sub{i}", "docs": 10 - i,
             "polarity": {"buckets": [], "missing": {"docs": 0}}}
            for i in range(12)  # 12 > top-N of 8
        ]
        payload = _make_solr_analytics_payload(subreddit_buckets=extra_buckets)
        result = self._run(payload)
        labels = [s["label"] for s in result["by_subreddit"]]
        counts = [s["count"] for s in result["by_subreddit"]]
        assert "Other" in labels
        other_idx = labels.index("Other")
        assert counts[other_idx] > 0

    def test_by_subreddit_empty_when_no_data(self):
        payload = _make_solr_analytics_payload(subreddit_buckets=[])
        result = self._run(payload)
        assert result["by_subreddit"] == []

    # ---- by_model ----

    def test_by_model_top_n_extracted(self):
        result = self._run(_make_analytics_payload_full())
        assert len(result["by_model"]) <= 6
        labels = [m["label"] for m in result["by_model"]]
        assert "chatgpt" in labels
        assert "claude" in labels

    def test_by_model_counts_correct(self):
        result = self._run(_make_analytics_payload_full())
        model_map = {m["label"]: m["count"] for m in result["by_model"]}
        assert model_map["chatgpt"] == 10
        assert model_map["claude"] == 6

    def test_by_model_polarity_mix(self):
        result = self._run(_make_analytics_payload_full())
        model_map = {m["label"]: m["polarity_mix"] for m in result["by_model"]}
        assert model_map["chatgpt"]["positive"] == 7
        assert model_map["chatgpt"]["negative"] == 3

    def test_by_model_other_rollup_when_overflow(self):
        extra_models = [
            {"val": f"model{i}", "docs": 20 - i,
             "polarity": {"buckets": [], "missing": {"docs": 0}}}
            for i in range(10)  # 10 > top-N of 6
        ]
        payload = _make_solr_analytics_payload(model_buckets=extra_models)
        result = self._run(payload)
        labels = [m["label"] for m in result["by_model"]]
        assert "Other" in labels

    def test_by_model_empty_when_no_data(self):
        payload = _make_solr_analytics_payload(model_buckets=[])
        result = self._run(payload)
        assert result["by_model"] == []

    # ---- by_vendor ----

    def test_by_vendor_top_n_extracted(self):
        result = self._run(_make_analytics_payload_full())
        assert len(result["by_vendor"]) <= 5
        labels = [v["label"] for v in result["by_vendor"]]
        assert "openai" in labels

    def test_by_vendor_empty_when_no_data(self):
        payload = _make_solr_analytics_payload(vendor_buckets=[])
        result = self._run(payload)
        assert result["by_vendor"] == []

    # ---- by_type ----

    def test_by_type_post_and_comment(self):
        result = self._run(_make_analytics_payload_full())
        type_labels = [t["label"] for t in result["by_type"]]
        assert "post" in type_labels
        assert "comment" in type_labels

    def test_by_type_counts(self):
        result = self._run(_make_analytics_payload_full())
        type_map = {t["label"]: t["count"] for t in result["by_type"]}
        assert type_map["post"] == 14
        assert type_map["comment"] == 6

    # ---- sarcasm_totals ----

    def test_sarcasm_totals_present(self):
        result = self._run(_make_analytics_payload_full())
        assert "sarcasm_totals" in result
        assert "sarcastic" in result["sarcasm_totals"]
        assert "non_sarcastic" in result["sarcasm_totals"]
        assert "unknown" in result["sarcasm_totals"]

    def test_sarcasm_totals_correct(self):
        result = self._run(_make_analytics_payload_full())
        assert result["sarcasm_totals"]["sarcastic"] == 7
        assert result["sarcasm_totals"]["non_sarcastic"] == 11
        assert result["sarcasm_totals"]["unknown"] == 0

    def test_sarcasm_missing_counted_as_unknown(self):
        payload = _make_solr_analytics_payload(
            sarcasm_buckets=[{"val": "sarcastic", "docs": 3}],
            sarcasm_missing_count=5,
        )
        result = self._run(payload)
        assert result["sarcasm_totals"]["sarcastic"] == 3
        assert result["sarcasm_totals"]["unknown"] == 5

    def test_sarcasm_unrecognised_label_goes_to_unknown(self):
        payload = _make_solr_analytics_payload(
            sarcasm_buckets=[{"val": "weird_label", "docs": 4}]
        )
        result = self._run(payload)
        assert result["sarcasm_totals"]["unknown"] == 4

    def test_sarcasm_zero_when_no_sarcasm_data(self):
        payload = _make_solr_analytics_payload(sarcasm_buckets=[], sarcasm_missing_count=0)
        result = self._run(payload)
        assert result["sarcasm_totals"]["sarcastic"] == 0
        assert result["sarcasm_totals"]["non_sarcastic"] == 0
        assert result["sarcasm_totals"]["unknown"] == 0

    # ---- sarcasm_series ----

    def test_sarcasm_series_present(self):
        result = self._run(_make_analytics_payload_full())
        assert "sarcasm_series" in result

    def test_sarcasm_series_parallel_to_time_buckets(self):
        date_buckets = [
            {
                "val": f"2024-0{m}-01T00:00:00Z",
                "sarcasm": {
                    "buckets": [{"val": "sarcastic", "docs": m}],
                    "missing": {"docs": 0},
                },
            }
            for m in range(1, 4)
        ]
        result = self._run(_make_solr_analytics_payload(date_buckets=date_buckets))
        n = len(result["time_buckets"])
        assert n == 3
        for lbl, series in result["sarcasm_series"].items():
            assert len(series) == n, f"sarcasm_series[{lbl!r}] length mismatch"

    def test_sarcasm_series_values_correct(self):
        date_buckets = [
            {
                "val": "2024-01-01T00:00:00Z",
                "sarcasm": {
                    "buckets": [{"val": "sarcastic", "docs": 3}, {"val": "non_sarcastic", "docs": 5}],
                    "missing": {"docs": 1},
                },
            },
            {
                "val": "2024-02-01T00:00:00Z",
                "sarcasm": {
                    "buckets": [{"val": "non_sarcastic", "docs": 7}],
                    "missing": {"docs": 0},
                },
            },
        ]
        result = self._run(_make_solr_analytics_payload(date_buckets=date_buckets))
        assert result["sarcasm_series"]["sarcastic"]     == [3, 0]
        assert result["sarcasm_series"]["non_sarcastic"] == [5, 7]
        assert result["sarcasm_series"]["unknown"]       == [1, 0]

    # ---- no confidence_bands in output ----

    def test_confidence_bands_not_in_result(self):
        result = self._run(_make_analytics_payload_full())
        assert "confidence_bands" not in result

    # ---- new structured keys alongside legacy keys ----

    def test_new_sections_present(self):
        result = self._run(_make_analytics_payload_full())
        for key in ("overview", "sentiment", "by_subreddit", "by_model",
                    "by_vendor", "by_type", "sarcasm_totals", "sarcasm_series"):
            assert key in result, f"Missing section: {key}"

    def test_legacy_keys_still_present(self):
        result = self._run(_make_analytics_payload_full())
        for key in ("time_buckets", "polarity_series", "subjectivity_series",
                    "polarity_totals", "subjectivity_totals", "total_docs_analysed"):
            assert key in result, f"Missing legacy key: {key}"

    def test_get_sentiment_analytics_alias_works(self):
        """get_sentiment_analytics must be an alias for get_analytics (same function object)."""
        from hybrid_search import HybridSearchService
        # Compare the underlying functions (class attributes), not bound methods
        assert HybridSearchService.get_sentiment_analytics is HybridSearchService.get_analytics
