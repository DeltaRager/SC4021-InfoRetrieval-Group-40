"""
Benchmark script for AI Opinion Search Engine.

Runs baseline retrieval queries, opinion-specific queries, and hybrid-specific
queries, printing result count and latency for each.

Hybrid mode (--hybrid) exercises the Flask app's GET / endpoint so the full
BM25 + Vector + RRF + Rerank pipeline is measured end-to-end.
Direct-Solr mode (default) hits Solr directly for lightweight BM25 benchmarking.
"""

import argparse
import time

import requests

DEFAULT_SOLR_URL = "http://localhost:8983/solr/reddit_ai/select"
DEFAULT_FLASK_URL = "http://localhost:5001"

# Baseline queries (original 3.2 requirements)
BASELINE_QUERIES = [
    "ChatGPT privacy",
    "Claude security",
    "AI agents risk",
    "prompt injection",
    "OpenAI regulation",
]

# Opinion-specific queries
OPINION_QUERIES = [
    "positive opinions on Claude",
    "negative sentiment about ChatGPT",
    "AI job loss concerns",
    "privacy concerns in ChatGPT subreddit",
    "Gemini vs ChatGPT opinion",
]

# Hybrid-specific queries — designed to exercise semantic retrieval gaps in BM25
HYBRID_QUERIES = [
    "ChatGPT vs Claude",
    "Gemini vs ChatGPT opinions",
    "which AI assistant is better for coding",
    "large language model comparison user experience",
    "AI model safety alignment concerns",
]


def run_query_solr(solr_url: str, q: str, extra_params: dict = None) -> tuple[int, float]:
    params = {
        "q":       q,
        "defType": "edismax",
        "qf":      "title^4 search_text^3 body^1.5",
        "pf":      "title^8 search_text^4",
        "mm":      "2<75%",
        "rows":    10,
        "wt":      "json",
    }
    if extra_params:
        params.update(extra_params)

    start = time.perf_counter()
    resp = requests.get(solr_url, params=params, timeout=15)
    resp.raise_for_status()
    latency = (time.perf_counter() - start) * 1000
    count = resp.json().get("response", {}).get("numFound", 0)
    return count, latency


def run_query_flask(flask_url: str, q: str, extra_params: dict = None) -> tuple[int, float]:
    """Hit the Flask app's GET / endpoint and extract result count from the response."""
    params = {"q": q, "nlp": "1"}
    if extra_params:
        params.update(extra_params)

    start = time.perf_counter()
    resp = requests.get(flask_url.rstrip("/") + "/", params=params, timeout=30)
    resp.raise_for_status()
    latency = (time.perf_counter() - start) * 1000

    # Extract numFound from the HTML response (the meta div)
    import re
    m = re.search(r"Found <b>(\d+)</b>", resp.text)
    count = int(m.group(1)) if m else 0
    return count, latency


def _print_section(title: str, queries: list, run_fn, extra_params_list=None, label_width=45):
    print()
    print("=" * 70)
    print(title)
    print("-" * 70)
    print(f"{'Query':<{label_width}} {'Results':>8} {'Latency(ms)':>12}")
    print("-" * 70)
    for i, q in enumerate(queries):
        extra = (extra_params_list[i] if extra_params_list else None)
        label = q if extra is None else f"{q} [{extra.get('fq', '')}]"
        try:
            count, latency = run_fn(q, extra) if extra is not None else run_fn(q)
            print(f"{label:<{label_width}} {count:>8} {latency:>11.2f}")
        except Exception as exc:
            print(f"{label:<{label_width}} ERROR: {exc}")


def run_bench_solr(solr_url: str) -> None:
    def _run(q, extra=None):
        return run_query_solr(solr_url, q, extra)

    _print_section("BASELINE QUERIES (BM25 / Solr direct)", BASELINE_QUERIES, _run)
    _print_section("OPINION-SPECIFIC QUERIES (BM25 / Solr direct)", OPINION_QUERIES, _run)
    _print_section("HYBRID-SPECIFIC QUERIES (BM25 / Solr direct)", HYBRID_QUERIES, _run)

    print()
    print("=" * 70)
    print("FACET / FILTER SPOT CHECKS")
    print("-" * 70)
    spot_checks = [
        ("ChatGPT privacy", {"fq": "polarity_label:negative"}),
        ("Claude",          {"fq": "model_mentions:claude"}),
        ("AI regulation",   {"fq": "source_dataset:mega_ai_posts_comments_classified"}),
    ]
    for q, extra in spot_checks:
        label = f"{q} [{extra.get('fq', '')}]"
        try:
            count, latency = run_query_solr(solr_url, q, extra)
            print(f"{label:<55} {count:>6} {latency:>10.2f}")
        except Exception as exc:
            print(f"{label:<55} ERROR: {exc}")


def run_bench_hybrid(flask_url: str) -> None:
    def _run(q, _extra=None):
        return run_query_flask(flask_url, q)

    _print_section(
        "HYBRID QUERIES (Flask app — full BM25+Vector+RRF+Rerank pipeline)",
        HYBRID_QUERIES,
        _run,
    )
    _print_section("BASELINE QUERIES (Flask app)", BASELINE_QUERIES, _run)
    _print_section("OPINION-SPECIFIC QUERIES (Flask app)", OPINION_QUERIES, _run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark queries against Solr or the Flask app")
    parser.add_argument("--solr-url",   default=DEFAULT_SOLR_URL)
    parser.add_argument("--flask-url",  default=DEFAULT_FLASK_URL)
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Benchmark via the Flask app (full hybrid pipeline) instead of Solr directly",
    )
    args = parser.parse_args()

    if args.hybrid:
        run_bench_hybrid(args.flask_url)
    else:
        run_bench_solr(args.solr_url)
