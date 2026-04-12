#!/usr/bin/env python3
"""Evaluate paired BM25 vs hybrid retrieval runs from the Flask search UI.

The evaluator works in two phases:

1. Collect paired search results from the Flask app:
   - BM25-only:  nlp=1, vector=0
   - Hybrid:     nlp=1, vector=1
2. Merge externally supplied judgments and render a markdown report.

This script deliberately talks to the Flask app's ``GET /`` route so the
evaluation matches the real UI toggle semantics instead of bypassing the app.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import statistics
import sys
import textwrap
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

DEFAULT_FLASK_URL = "http://localhost:5001"
DEFAULT_SOLR_CORE_URL = "http://localhost:8983/solr/reddit_ai/select"
DEFAULT_EMBEDDING_URL = "http://localhost:8081"
DEFAULT_RERANKER_URL = "http://localhost:8082"
DEFAULT_LIMIT = 20

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUERY_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hybrid_eval_queries.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "hybrid_eval"
DEFAULT_RAW_PATH = DEFAULT_OUTPUT_DIR / "paired_results.json"
DEFAULT_JUDGMENTS_PATH = DEFAULT_OUTPUT_DIR / "judgments.json"
DEFAULT_REPORT_PATH = ROOT / "reports" / "hybrid_vs_bm25_evaluation.md"

REQUEST_PARAMS = {
    "nlp": "1",
    "sort": "score desc",
}

HEALTH_ENDPOINTS = {
    "flask": lambda base: (base.rstrip("/") + "/", {}),
    "solr": lambda base: (base.rstrip("/"), {"q": "*:*", "rows": 0, "wt": "json"}),
    "embedding": lambda base: (base.rstrip("/") + "/v1/embeddings", {}),
    "reranker": lambda base: (base.rstrip("/") + "/v1/reranking", {}),
}


@dataclass
class ModeRun:
    mode_key: str
    label: str
    diagnostics: dict[str, Any]
    results: list[dict[str, Any]]
    total_results: int
    response_ms: float | None
    warnings: list[str]
    raw_url: str


class SearchPageParser(HTMLParser):
    """Extract retrieval diagnostics and visible result cards from HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, Any]] = []
        self.retrieval_spans: list[dict[str, str]] = []
        self.current_result: dict[str, Any] | None = None
        self.current_section: str | None = None
        self.current_span_classes: set[str] = set()
        self.current_span_parts: list[str] = []
        self.result_div_depth = 0
        self.in_retrieval = False
        self.retrieval_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        classes = set(attr_map.get("class", "").split())
        if tag == "div" and "retrieval-status" in classes:
            self.in_retrieval = True
            self.retrieval_depth = 1
            return
        if self.in_retrieval and tag == "div":
            self.retrieval_depth += 1
        if tag == "span" and self.in_retrieval:
            self.current_span_classes = classes
            self.current_span_parts = []
        if tag == "div" and "result" in classes:
            self.current_result = {
                "tags": [],
                "badges": [],
                "model_mentions": [],
                "concepts": [],
                "snippet": "",
            }
            self.current_section = None
            self.result_div_depth = 1
            return
        if self.current_result is None:
            return
        if tag == "div":
            self.result_div_depth += 1
            if "tags" in classes:
                self.current_section = "tags"
            elif "snippet" in classes:
                self.current_section = "snippet"
            elif "doc-concepts" in classes:
                self.current_section = "concepts"
        elif tag == "span" and self.current_section == "tags":
            self.current_span_classes = classes
            self.current_span_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self.current_span_parts is not None and self.current_span_classes is not None:
            text = _normalize_ws("".join(self.current_span_parts))
            if self.in_retrieval:
                if text:
                    self.retrieval_spans.append({"classes": sorted(self.current_span_classes), "text": text})
            elif self.current_result is not None and self.current_section == "tags" and text:
                if "model-tag" in self.current_span_classes:
                    self.current_result["model_mentions"].append(text)
                elif "badge" in self.current_span_classes:
                    self.current_result["badges"].append(text)
                else:
                    self.current_result["tags"].append(text)
            self.current_span_classes = set()
            self.current_span_parts = []
            return
        if tag == "div" and self.in_retrieval:
            self.retrieval_depth -= 1
            if self.retrieval_depth == 0:
                self.in_retrieval = False
            return
        if self.current_result is None:
            return
        if tag == "div":
            self.result_div_depth -= 1
            if self.result_div_depth == 0:
                self.current_result["snippet"] = _normalize_ws(self.current_result["snippet"])
                self.results.append(self.current_result)
                self.current_result = None
                self.current_section = None
            elif self.current_section in {"tags", "snippet", "concepts"}:
                self.current_section = None

    def handle_data(self, data: str) -> None:
        if self.in_retrieval and self.current_span_parts is not None:
            self.current_span_parts.append(data)
            return
        if self.current_result is None:
            return
        if self.current_section == "snippet":
            self.current_result["snippet"] += data
        elif self.current_section == "concepts":
            text = _normalize_ws(data)
            if not text or text == "Concepts:":
                return
            self.current_result["concepts"].append(text)
        elif self.current_section == "tags" and self.current_span_parts is not None:
            self.current_span_parts.append(data)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _signature(result: dict[str, Any]) -> str:
    joined = " | ".join([
        result.get("snippet", ""),
        "|".join(result.get("tags", [])),
        "|".join(result.get("badges", [])),
        "|".join(result.get("model_mentions", [])),
    ])
    return _normalize_ws(joined).lower()[:240]


def load_queries(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, str]] = []
    for group in payload.get("query_groups", []):
        category = group["category"]
        for query in group.get("queries", []):
            items.append({
                "category": category,
                "query": query,
                "slug": _slugify(f"{category}-{query}")[:80],
            })
    return items


def health_check(urls: dict[str, str]) -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for name, base_url in urls.items():
        endpoint, params = HEALTH_ENDPOINTS[name](base_url)
        try:
            resp = requests.get(endpoint, params=params, timeout=10)
            status[name] = {
                "ok": True,
                "status_code": resp.status_code,
                "url": resp.url,
            }
        except requests.RequestException as exc:
            status[name] = {
                "ok": False,
                "status_code": None,
                "url": endpoint,
                "error": str(exc),
            }
    return status


def parse_search_page(page_html: str, *, limit: int) -> tuple[dict[str, Any], list[dict[str, Any]], int, float | None]:
    parser = SearchPageParser()
    parser.feed(page_html)

    meta_match = re.search(
        r"Found\s*<b>(\d+)</b>\s*results\s*in\s*<b>([\d.]+)\s*ms</b>",
        page_html,
        flags=re.IGNORECASE,
    )
    total_results = int(meta_match.group(1)) if meta_match else 0
    response_ms = float(meta_match.group(2)) if meta_match else None

    diagnostics: dict[str, Any] = {
        "mode": "",
        "degraded": False,
        "warnings": [],
        "latency_ms": {},
    }
    for span in parser.retrieval_spans:
        classes = set(span["classes"])
        text = span["text"]
        if "hybrid" in classes and "retrieval-badge" in classes:
            diagnostics["mode"] = "hybrid"
        elif "lexical" in classes and "retrieval-badge" in classes:
            diagnostics["mode"] = "lexical"
        elif "degraded" in classes and "retrieval-badge" in classes:
            diagnostics["degraded"] = True
        elif any(c.startswith("intent-") for c in classes):
            diagnostics["intent_label"] = text.lower()
        elif text.startswith("Lexical:"):
            diagnostics["lexical_hits"] = _extract_int(text)
        elif text.startswith("Vector:"):
            diagnostics["vector_hits"] = _extract_int(text)
        elif text.startswith("Fused:"):
            diagnostics["fused_hits"] = _extract_int(text)
        elif text.startswith("Reranked:"):
            diagnostics["reranked_hits"] = _extract_int(text)
        elif text.startswith("α="):
            alpha_match = re.search(r"α=([\d.]+)\s+β=([\d.]+)", text)
            if alpha_match:
                diagnostics["alpha"] = float(alpha_match.group(1))
                diagnostics["beta"] = float(alpha_match.group(2))
        elif "lex " in text or "vec " in text or "rerank " in text:
            diagnostics["latency_ms"] = _parse_latency_breakdown(text)

    results = []
    for idx, result in enumerate(parser.results[:limit], start=1):
        item = {
            "rank": idx,
            "snippet": result.get("snippet", ""),
            "tags": result.get("tags", []),
            "badges": result.get("badges", []),
            "model_mentions": result.get("model_mentions", []),
            "concepts": result.get("concepts", []),
        }
        item["signature"] = _signature(item)
        results.append(item)

    return diagnostics, results, total_results, response_ms


def _extract_int(text: str) -> int:
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 0


def _parse_latency_breakdown(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, label in (("lexical", "lex"), ("vector", "vec"), ("rrf", "rrf"), ("rerank", "rerank")):
        match = re.search(rf"{label}\s+([\d.]+)ms", text)
        if match:
            metrics[key] = float(match.group(1))
    return metrics


def fetch_mode_run(
    flask_url: str,
    query: str,
    *,
    vector_enabled: bool,
    limit: int,
    session: requests.Session,
) -> ModeRun:
    params = dict(REQUEST_PARAMS)
    params["q"] = query
    params["vector"] = "1" if vector_enabled else "0"

    resp = session.get(flask_url.rstrip("/") + "/", params=params, timeout=60)
    resp.raise_for_status()
    diagnostics, results, total_results, response_ms = parse_search_page(resp.text, limit=limit)
    warnings = []
    if diagnostics.get("degraded"):
        warnings.append("Degraded retrieval path reported by the UI.")

    return ModeRun(
        mode_key="hybrid" if vector_enabled else "bm25",
        label="Hybrid" if vector_enabled else "BM25",
        diagnostics=diagnostics,
        results=results,
        total_results=total_results,
        response_ms=response_ms,
        warnings=warnings,
        raw_url=resp.url,
    )


def collect_pairs(
    queries: list[dict[str, str]],
    *,
    flask_url: str,
    service_urls: dict[str, str],
    limit: int,
    output_path: Path,
    health: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    session = requests.Session()
    paired_rows = []
    for item in queries:
        bm25 = fetch_mode_run(flask_url, item["query"], vector_enabled=False, limit=limit, session=session)
        hybrid = fetch_mode_run(flask_url, item["query"], vector_enabled=True, limit=limit, session=session)
        paired_rows.append({
            "query": item["query"],
            "category": item["category"],
            "slug": item["slug"],
            "request_params": REQUEST_PARAMS,
            "bm25": _mode_run_as_dict(bm25),
            "hybrid": _mode_run_as_dict(hybrid),
        })

    payload = {
        "environment": {
            "flask_url": flask_url,
            "solr_core_url": service_urls["solr"],
            "embedding_url": service_urls["embedding"],
            "reranker_url": service_urls["reranker"],
            "request_params": {**REQUEST_PARAMS, "vector": "0/1"},
            "health": health,
            "initial_state_note": (
                "Before implementation-time evaluation, localhost services for Flask, Solr, "
                "embedding, and reranker were not running in this environment."
            ),
        },
        "queries": paired_rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _mode_run_as_dict(run: ModeRun) -> dict[str, Any]:
    return {
        "mode_key": run.mode_key,
        "label": run.label,
        "diagnostics": run.diagnostics,
        "results": run.results,
        "total_results": run.total_results,
        "response_ms": run.response_ms,
        "warnings": run.warnings,
        "raw_url": run.raw_url,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_judgments(raw_payload: dict[str, Any], judgments_payload: dict[str, Any]) -> dict[str, Any]:
    judgments_by_query = {item["query"]: item for item in judgments_payload.get("judgments", [])}
    merged_queries = []
    for entry in raw_payload.get("queries", []):
        judgment = judgments_by_query.get(entry["query"])
        if judgment is None:
            raise ValueError(f"Missing judgment for query: {entry['query']}")
        merged_queries.append(_merge_query_judgment(entry, judgment))

    return {
        "environment": raw_payload.get("environment", {}),
        "queries": merged_queries,
    }


def _merge_query_judgment(entry: dict[str, Any], judgment: dict[str, Any]) -> dict[str, Any]:
    merged = dict(entry)
    merged["judgment"] = {
        "winner": judgment["winner"],
        "rationale": judgment["rationale"],
        "spot_check_notes": judgment.get("spot_check_notes", []),
    }
    for mode_key in ("bm25", "hybrid"):
        scores = judgment.get(mode_key, [])
        results = entry[mode_key]["results"]
        if len(scores) < len(results):
            raise ValueError(
                f"Judgment count mismatch for query '{entry['query']}' mode '{mode_key}': "
                f"expected {len(results)}, got {len(scores)}."
            )
        if len(scores) > len(results):
            scores = scores[: len(results)]
        enriched = []
        for result, row in zip(results, scores, strict=True):
            enriched.append({**result, "judgment": {"score": row["score"], "evidence": row["evidence"]}})
        merged[mode_key] = {**entry[mode_key], "results": enriched, "summary": summarize_results(enriched)}

    merged["comparison"] = compare_modes(merged["bm25"], merged["hybrid"])
    return merged


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [int(item["judgment"]["score"]) for item in results]
    relevant_ranks = [item["rank"] for item in results if item["judgment"]["score"] >= 1]
    highly_relevant_ranks = [item["rank"] for item in results if item["judgment"]["score"] == 2]
    band_totals = {
        "1-5": sum(int(item["judgment"]["score"]) for item in results if 1 <= item["rank"] <= 5),
        "6-10": sum(int(item["judgment"]["score"]) for item in results if 6 <= item["rank"] <= 10),
        "11-20": sum(int(item["judgment"]["score"]) for item in results if 11 <= item["rank"] <= 20),
    }
    return {
        "total_relevance_score": sum(scores),
        "relevant_count": sum(1 for score in scores if score >= 1),
        "highly_relevant_count": sum(1 for score in scores if score == 2),
        "first_relevant_rank": relevant_ranks[0] if relevant_ranks else None,
        "first_highly_relevant_rank": highly_relevant_ranks[0] if highly_relevant_ranks else None,
        "band_totals": band_totals,
    }


def compare_modes(bm25: dict[str, Any], hybrid: dict[str, Any]) -> dict[str, Any]:
    bm25_relevant = {
        item["signature"]: item
        for item in bm25["results"]
        if item["judgment"]["score"] >= 1
    }
    hybrid_relevant = {
        item["signature"]: item
        for item in hybrid["results"]
        if item["judgment"]["score"] >= 1
    }
    overlap = sorted(set(bm25_relevant) & set(hybrid_relevant))
    hybrid_unique = sorted(set(hybrid_relevant) - set(bm25_relevant))
    bm25_unique = sorted(set(bm25_relevant) - set(hybrid_relevant))
    return {
        "score_delta": hybrid["summary"]["total_relevance_score"] - bm25["summary"]["total_relevance_score"],
        "relevant_delta": hybrid["summary"]["relevant_count"] - bm25["summary"]["relevant_count"],
        "highly_relevant_delta": hybrid["summary"]["highly_relevant_count"] - bm25["summary"]["highly_relevant_count"],
        "overlap_relevant_count": len(overlap),
        "hybrid_unique_relevant_count": len(hybrid_unique),
        "bm25_unique_relevant_count": len(bm25_unique),
        "hybrid_unique_examples": _examples_from_signatures(hybrid_relevant, hybrid_unique),
        "bm25_unique_examples": _examples_from_signatures(bm25_relevant, bm25_unique),
    }


def _examples_from_signatures(items: dict[str, dict[str, Any]], signatures: list[str], limit: int = 3) -> list[str]:
    examples = []
    for key in signatures[:limit]:
        item = items[key]
        examples.append(f"r{item['rank']}: {trim_text(item['snippet'], 120)}")
    return examples


def trim_text(text: str, length: int = 120) -> str:
    text = _normalize_ws(text)
    if len(text) <= length:
        return text
    return text[: length - 3].rstrip() + "..."


def render_report(payload: dict[str, Any]) -> str:
    env = payload["environment"]
    queries = payload["queries"]
    category_rows = build_category_summary(queries)

    lines = [
        "# Hybrid vs BM25 Evaluation",
        "",
        "## Environment / Setup",
        "",
        f"- Flask URL: `{env.get('flask_url', '')}`",
        f"- Solr core URL: `{env.get('solr_core_url', '')}`",
        f"- Embedding URL: `{env.get('embedding_url', '')}`",
        f"- Reranker URL: `{env.get('reranker_url', '')}`",
        f"- Request parameters: `{json.dumps(env.get('request_params', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Initial state note: {env.get('initial_state_note', '')}",
        "",
        "### Service Health",
        "",
        "| Service | OK | Status | URL |",
        "| --- | --- | --- | --- |",
    ]
    for name, row in env.get("health", {}).items():
        status = row.get("status_code", "")
        url = row.get("url", "")
        ok = "yes" if row.get("ok") else "no"
        lines.append(f"| {name} | {ok} | {status} | `{url}` |")

    lines.extend([
        "",
        "## Method",
        "",
        "- Paired design: each query ran twice through the Flask UI endpoint, once with `vector=0` and once with `vector=1`.",
        "- Shared controls: `nlp=1`, `sort=score desc`, no filters, same query text per pair.",
        "- Judgment depth: top 20 visible results per mode were scored `0/1/2`.",
        "- Judging protocol: LLM judge with brief evidence per result, plus manual spot checks on sampled disagreements and close calls.",
        "",
        "## Category Summary",
        "",
        "| Category | Queries | BM25 wins | Hybrid wins | Ties | Avg BM25 score@20 | Avg Hybrid score@20 | Avg BM25 ms | Avg Hybrid ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in category_rows:
        lines.append(
            f"| {row['category']} | {row['queries']} | {row['bm25_wins']} | {row['hybrid_wins']} | "
            f"{row['ties']} | {row['avg_bm25_score']:.2f} | {row['avg_hybrid_score']:.2f} | "
            f"{row['avg_bm25_ms']:.2f} | {row['avg_hybrid_ms']:.2f} |"
        )

    lines.extend([
        "",
        "## Per-Query Comparison",
        "",
    ])
    for entry in queries:
        lines.extend(render_query_section(entry))

    lines.extend(render_conclusion(queries, category_rows))
    return "\n".join(lines) + "\n"


def build_category_summary(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in queries:
        grouped.setdefault(entry["category"], []).append(entry)

    rows = []
    for category, items in grouped.items():
        rows.append({
            "category": category,
            "queries": len(items),
            "bm25_wins": sum(1 for item in items if item["judgment"]["winner"] == "bm25"),
            "hybrid_wins": sum(1 for item in items if item["judgment"]["winner"] == "hybrid"),
            "ties": sum(1 for item in items if item["judgment"]["winner"] == "tie"),
            "avg_bm25_score": statistics.mean(item["bm25"]["summary"]["total_relevance_score"] for item in items),
            "avg_hybrid_score": statistics.mean(item["hybrid"]["summary"]["total_relevance_score"] for item in items),
            "avg_bm25_ms": statistics.mean((item["bm25"].get("response_ms") or 0.0) for item in items),
            "avg_hybrid_ms": statistics.mean((item["hybrid"].get("response_ms") or 0.0) for item in items),
        })
    return sorted(rows, key=lambda row: row["category"])


def render_query_section(entry: dict[str, Any]) -> list[str]:
    bm25 = entry["bm25"]
    hybrid = entry["hybrid"]
    cmp_row = entry["comparison"]
    lines = [
        f"### {entry['query']}",
        "",
        f"- Category: `{entry['category']}`",
        f"- Winner: `{entry['judgment']['winner']}`",
        f"- Rationale: {entry['judgment']['rationale']}",
        f"- BM25 diagnostics: {render_diagnostics(bm25)}",
        f"- Hybrid diagnostics: {render_diagnostics(hybrid)}",
        (
            f"- Score@20: BM25 {bm25['summary']['total_relevance_score']} vs Hybrid "
            f"{hybrid['summary']['total_relevance_score']} (delta {cmp_row['score_delta']:+d})"
        ),
        (
            f"- Relevant@20: BM25 {bm25['summary']['relevant_count']} vs Hybrid "
            f"{hybrid['summary']['relevant_count']} (delta {cmp_row['relevant_delta']:+d})"
        ),
        (
            f"- Highly relevant@20: BM25 {bm25['summary']['highly_relevant_count']} vs Hybrid "
            f"{hybrid['summary']['highly_relevant_count']} (delta {cmp_row['highly_relevant_delta']:+d})"
        ),
        (
            f"- First relevant rank: BM25 {bm25['summary']['first_relevant_rank']} | "
            f"Hybrid {hybrid['summary']['first_relevant_rank']}"
        ),
        (
            f"- Band totals: BM25 {bm25['summary']['band_totals']} | "
            f"Hybrid {hybrid['summary']['band_totals']}"
        ),
        (
            f"- Relevant overlap: {cmp_row['overlap_relevant_count']} shared, "
            f"{cmp_row['hybrid_unique_relevant_count']} hybrid-only, "
            f"{cmp_row['bm25_unique_relevant_count']} BM25-only"
        ),
    ]
    if cmp_row["hybrid_unique_examples"]:
        lines.append(f"- Hybrid-only relevant examples: {'; '.join(cmp_row['hybrid_unique_examples'])}")
    if cmp_row["bm25_unique_examples"]:
        lines.append(f"- BM25-only relevant examples: {'; '.join(cmp_row['bm25_unique_examples'])}")
    if entry["judgment"].get("spot_check_notes"):
        lines.append(f"- Spot checks: {'; '.join(entry['judgment']['spot_check_notes'])}")
    lines.extend([
        "",
        "| Mode | Rank | Score | Evidence | Visible result |",
        "| --- | ---: | ---: | --- | --- |",
    ])
    for mode_key, label in (("bm25", "BM25"), ("hybrid", "Hybrid")):
        for item in entry[mode_key]["results"]:
            lines.append(
                f"| {label} | {item['rank']} | {item['judgment']['score']} | "
                f"{escape_pipes(item['judgment']['evidence'])} | {escape_pipes(trim_text(item['snippet'], 140))} |"
            )
    lines.append("")
    return lines


def render_diagnostics(run: dict[str, Any]) -> str:
    diag = run.get("diagnostics", {})
    pieces = [
        f"mode={diag.get('mode', '')}",
        f"response_ms={run.get('response_ms')}",
        f"lexical_hits={diag.get('lexical_hits', 0)}",
        f"vector_hits={diag.get('vector_hits', 0)}",
        f"fused_hits={diag.get('fused_hits', 0)}",
        f"reranked_hits={diag.get('reranked_hits', 0)}",
    ]
    if diag.get("intent_label"):
        pieces.append(f"intent={diag['intent_label']}")
    if "alpha" in diag and "beta" in diag:
        pieces.append(f"alpha={diag['alpha']}")
        pieces.append(f"beta={diag['beta']}")
    return ", ".join(str(piece) for piece in pieces)


def escape_pipes(text: str) -> str:
    return text.replace("|", "\\|")


def render_conclusion(queries: list[dict[str, Any]], category_rows: list[dict[str, Any]]) -> list[str]:
    hybrid_wins = sum(1 for item in queries if item["judgment"]["winner"] == "hybrid")
    bm25_wins = sum(1 for item in queries if item["judgment"]["winner"] == "bm25")
    ties = sum(1 for item in queries if item["judgment"]["winner"] == "tie")
    total = len(queries)
    avg_bm25 = statistics.mean(item["bm25"]["summary"]["total_relevance_score"] for item in queries)
    avg_hybrid = statistics.mean(item["hybrid"]["summary"]["total_relevance_score"] for item in queries)
    avg_bm25_ms = statistics.mean((item["bm25"].get("response_ms") or 0.0) for item in queries)
    avg_hybrid_ms = statistics.mean((item["hybrid"].get("response_ms") or 0.0) for item in queries)

    strongest_hybrid = sorted(
        (item for item in queries if item["judgment"]["winner"] == "hybrid"),
        key=lambda item: item["comparison"]["score_delta"],
        reverse=True,
    )[:5]
    strongest_bm25 = sorted(
        (item for item in queries if item["judgment"]["winner"] == "bm25"),
        key=lambda item: item["comparison"]["score_delta"],
    )[:3]

    lines = [
        "## Conclusion",
        "",
        f"- Query outcomes: {hybrid_wins} hybrid wins, {bm25_wins} BM25 wins, {ties} ties across {total} queries.",
        f"- Average score@20: BM25 {avg_bm25:.2f} vs Hybrid {avg_hybrid:.2f}.",
        f"- Average latency: BM25 {avg_bm25_ms:.2f} ms vs Hybrid {avg_hybrid_ms:.2f} ms.",
    ]
    if strongest_hybrid:
        lines.append(
            "- Strongest hybrid wins: " +
            "; ".join(f"`{item['query']}` ({item['comparison']['score_delta']:+d})" for item in strongest_hybrid)
        )
    if strongest_bm25:
        lines.append(
            "- BM25-favored cases: " +
            "; ".join(f"`{item['query']}` ({item['comparison']['score_delta']:+d})" for item in strongest_bm25)
        )

    category_highlights = []
    for row in category_rows:
        if row["avg_hybrid_score"] > row["avg_bm25_score"]:
            category_highlights.append(
                f"`{row['category']}` favored hybrid ({row['avg_hybrid_score']:.2f} vs {row['avg_bm25_score']:.2f})"
            )
        elif row["avg_hybrid_score"] < row["avg_bm25_score"]:
            category_highlights.append(
                f"`{row['category']}` favored BM25 ({row['avg_bm25_score']:.2f} vs {row['avg_hybrid_score']:.2f})"
            )
        else:
            category_highlights.append(f"`{row['category']}` was effectively tied")
    lines.append("- Category readout: " + "; ".join(category_highlights))
    lines.extend([
        "",
        "Hybrid is justified when it consistently improves judged relevance for paraphrased, comparative, and aspect-heavy queries enough to offset its latency cost. BM25 remains preferable for literal, high-precision keyword lookups when hybrid adds latency without new relevant evidence.",
        "",
    ])
    return lines


def build_judging_prompt(raw_payload: dict[str, Any]) -> str:
    header = textwrap.dedent(
        """
        You are judging paired retrieval outputs for the same query.

        Score every visible result on this rubric:
        - 0 = irrelevant or off-topic for the query intent
        - 1 = partially relevant, indirect, or weak evidence
        - 2 = directly relevant and useful for the query intent

        Requirements:
        - Judge the top 20 results in each mode independently.
        - Use only the visible result text and tags provided.
        - Return valid JSON only.
        - Winner must be one of: "bm25", "hybrid", "tie".
        - Keep each evidence string to one sentence.
        - Add 1-3 short `spot_check_notes` when a close call should be manually reviewed.

        Output schema:
        {
          "judgments": [
            {
              "query": "...",
              "winner": "bm25|hybrid|tie",
              "rationale": "...",
              "spot_check_notes": ["...", "..."],
              "bm25": [{"score": 0, "evidence": "..."}, ...],
              "hybrid": [{"score": 0, "evidence": "..."}, ...]
            }
          ]
        }
        """
    ).strip()
    return header + "\n\n" + json.dumps({"queries": raw_payload["queries"]}, indent=2, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate hybrid retrieval vs BM25 via the Flask UI.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_QUERY_FIXTURE)
    parser.add_argument("--flask-url", default=DEFAULT_FLASK_URL)
    parser.add_argument("--solr-url", default=DEFAULT_SOLR_CORE_URL)
    parser.add_argument("--embedding-url", default=DEFAULT_EMBEDDING_URL)
    parser.add_argument("--reranker-url", default=DEFAULT_RERANKER_URL)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--judgments-input", type=Path, default=None)
    parser.add_argument("--judging-prompt-output", type=Path, default=DEFAULT_OUTPUT_DIR / "judge_prompt.txt")
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--skip-collection", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    urls = {
        "flask": args.flask_url,
        "solr": args.solr_url,
        "embedding": args.embedding_url,
        "reranker": args.reranker_url,
    }
    health = health_check(urls)

    raw_payload = None
    if args.skip_collection:
        raw_payload = load_json(args.raw_output)
    else:
        queries = load_queries(args.fixture)
        raw_payload = collect_pairs(
            queries,
            flask_url=args.flask_url,
            service_urls=urls,
            limit=args.limit,
            output_path=args.raw_output,
            health=health,
        )

    args.judging_prompt_output.parent.mkdir(parents=True, exist_ok=True)
    args.judging_prompt_output.write_text(build_judging_prompt(raw_payload), encoding="utf-8")

    if args.judgments_input is None:
        print(f"Wrote paired results to {args.raw_output}")
        print(f"Wrote judging prompt to {args.judging_prompt_output}")
        print("No judgments file supplied; skipping markdown report generation.")
        return 0

    judgments_payload = load_json(args.judgments_input)
    merged_payload = merge_judgments(raw_payload, judgments_payload)
    report_md = render_report(merged_payload)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(report_md, encoding="utf-8")
    print(f"Wrote paired results to {args.raw_output}")
    print(f"Wrote judging prompt to {args.judging_prompt_output}")
    print(f"Wrote report to {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
