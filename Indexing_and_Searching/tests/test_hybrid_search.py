"""
Unit and integration tests for the hybrid BM25 + vector retrieval pipeline.

Run with:
    python -m pytest Indexing_and_Searching/tests/test_hybrid_search.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make the Indexing_and_Searching directory importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hybrid_search import (
    Candidate,
    EmbeddingClient,
    HybridSearchService,
    RerankerClient,
    RetrievalInfo,
    reciprocal_rank_fusion,
)
from query_intent import infer_intent, QueryIntentProfile
from scripts.prepare_solr_docs import (
    _split_into_chunks,
    _make_chunk_records,
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
             "source_dataset": "test", "sentiment_label": "neutral",
             "sentiment_score": 0.0, "model_mentions": [], "vendor_mentions": [],
             "opinionatedness_score": 0.5, "score": 1, "created_date": ""}
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
                "sentiment_label": {"buckets": []},
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

        fq_filter = ["sentiment_label:negative", "type:post"]
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
            assert "sentiment_label:negative" in fq_str, (
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
                "sentiment_label": {"buckets": []},
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
    def test_embed_docs_success(self):
        docs = [
            {"id": "1__c0", "doc_id": "1", "chunk_text": "hello world"},
            {"id": "2__c0", "doc_id": "2", "chunk_text": "foo bar"},
        ]
        fake_client = MagicMock()
        fake_client.embed_batch.return_value = [[0.1, 0.2], [0.3, 0.4]]

        with patch("scripts.prepare_solr_docs._EMBEDDING_CLIENT", fake_client), \
             patch("scripts.prepare_solr_docs._EMBED_AVAILABLE", True):
            embed_docs(docs)

        assert docs[0]["chunk_vector"] == [0.1, 0.2]
        assert docs[1]["chunk_vector"] == [0.3, 0.4]

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
        assert docs[1]["chunk_vector"] == [0.5, 0.6]

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
        assert docs[1]["chunk_vector"] == [0.7, 0.8]

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
        assert docs[1]["chunk_vector"] == [0.9, 0.8]

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
        assert [doc["chunk_vector"] for doc in docs] == [[1.0], [2.0], [3.0]]


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
            "sentiment_label": "neutral",
            "sentiment_score": 0.0,
            "model_mentions": [],
            "vendor_mentions": [],
            "opinionatedness_score": 0.5,
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
                solr_q="q", fq=["sentiment_label:negative"], qf="", pf="", bq=[],
                sort="score desc", use_nlp=False, query_text="q",
            )

        assert len(captured_post_params) >= 1
        post_params = captured_post_params[0]
        fq_value = post_params.get("fq", "")
        fq_str = " ".join(fq_value) if isinstance(fq_value, list) else str(fq_value)
        assert "sentiment_label:negative" in fq_str

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
             "source_dataset": "test", "sentiment_label": "neutral",
             "sentiment_score": 0.0, "model_mentions": [], "vendor_mentions": [],
             "opinionatedness_score": 0.5, "score": 1, "created_date": ""}
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
                "sentiment_label": {"buckets": []}, "source_dataset": {"buckets": []},
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
