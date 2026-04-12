from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "evaluate_hybrid_vs_bm25.py"
spec = importlib.util.spec_from_file_location("evaluate_hybrid_vs_bm25", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_parse_search_page_extracts_diagnostics_and_results():
    html = """
    <div class="retrieval-status">
      <span class="retrieval-badge hybrid">Hybrid BM25 + Vector</span>
      <span class="retrieval-stat">Lexical: <b>100</b></span>
      <span class="retrieval-stat">Vector: <b>55</b></span>
      <span class="retrieval-stat">Fused: <b>42</b></span>
      <span class="retrieval-stat">Reranked: <b>20</b></span>
      <span class="retrieval-badge intent-semantic">Semantic</span>
      <span class="retrieval-stat">α=0.30 β=0.70</span>
      <span class="retrieval-stat">lex 12.5ms · vec 30.1ms · rrf 1.3ms · rerank 55.0ms</span>
    </div>
    <div class="meta"><span>Found <b>20</b> results in <b>111.4 ms</b>.</span></div>
    <div class="result">
      <div class="tags">
        <span>r/test</span>
        <span style="color:#888">reddit_ai_sentiment</span>
        <span class="badge badge-negative">negative</span>
        <span>score 12</span>
        <span>2025-01-01</span>
        <span class="model-tag">chatgpt</span>
      </div>
      <div class="snippet">People complain that ChatGPT hallucinates in production.</div>
      <div class="doc-concepts"><small><b>Concepts:</b></small> hallucination reliability</div>
    </div>
    """
    diagnostics, results, total_results, response_ms = module.parse_search_page(html, limit=20)
    assert diagnostics["mode"] == "hybrid"
    assert diagnostics["intent_label"] == "semantic"
    assert diagnostics["lexical_hits"] == 100
    assert diagnostics["vector_hits"] == 55
    assert diagnostics["latency_ms"]["rerank"] == 55.0
    assert total_results == 20
    assert response_ms == 111.4
    assert len(results) == 1
    assert results[0]["badges"] == ["negative"]
    assert results[0]["model_mentions"] == ["chatgpt"]
    assert "hallucinates" in results[0]["snippet"]


def test_summarize_and_compare_modes():
    bm25_results = [
        {"rank": 1, "signature": "a", "snippet": "one", "judgment": {"score": 2, "evidence": "exact"}},
        {"rank": 2, "signature": "b", "snippet": "two", "judgment": {"score": 0, "evidence": "off"}},
        {"rank": 3, "signature": "c", "snippet": "three", "judgment": {"score": 1, "evidence": "partial"}},
    ]
    hybrid_results = [
        {"rank": 1, "signature": "a", "snippet": "one", "judgment": {"score": 2, "evidence": "exact"}},
        {"rank": 2, "signature": "d", "snippet": "four", "judgment": {"score": 2, "evidence": "new"}},
        {"rank": 3, "signature": "e", "snippet": "five", "judgment": {"score": 1, "evidence": "new"}},
    ]
    bm25 = {"results": bm25_results, "summary": module.summarize_results(bm25_results)}
    hybrid = {"results": hybrid_results, "summary": module.summarize_results(hybrid_results)}
    comparison = module.compare_modes(bm25, hybrid)
    assert bm25["summary"]["total_relevance_score"] == 3
    assert hybrid["summary"]["total_relevance_score"] == 5
    assert comparison["score_delta"] == 2
    assert comparison["overlap_relevant_count"] == 1
    assert comparison["hybrid_unique_relevant_count"] == 2
