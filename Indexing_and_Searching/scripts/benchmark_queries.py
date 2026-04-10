"""
Benchmark script for AI Opinion Search Engine.

Runs both baseline retrieval queries and opinion-specific queries,
printing result count and latency for each.
"""

import argparse
import time

import requests

DEFAULT_SOLR_URL = "http://localhost:8983/solr/reddit_ai/select"

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


def run_query(solr_url: str, q: str, extra_params: dict = None) -> tuple[int, float]:
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


def run_bench(solr_url: str) -> None:
    print("=" * 65)
    print("BASELINE QUERIES")
    print("-" * 65)
    print(f"{'Query':<40} {'Results':>8} {'Latency(ms)':>12}")
    print("-" * 65)
    for q in BASELINE_QUERIES:
        try:
            count, latency = run_query(solr_url, q)
            print(f"{q:<40} {count:>8} {latency:>11.2f}")
        except Exception as exc:
            print(f"{q:<40} ERROR: {exc}")

    print()
    print("=" * 65)
    print("OPINION-SPECIFIC QUERIES")
    print("-" * 65)
    print(f"{'Query':<40} {'Results':>8} {'Latency(ms)':>12}")
    print("-" * 65)
    for q in OPINION_QUERIES:
        try:
            count, latency = run_query(solr_url, q)
            print(f"{q:<40} {count:>8} {latency:>11.2f}")
        except Exception as exc:
            print(f"{q:<40} ERROR: {exc}")

    print()
    print("=" * 65)
    print("FACET / FILTER SPOT CHECKS")
    print("-" * 65)
    spot_checks = [
        ("ChatGPT privacy", {"fq": "sentiment_label:negative"}),
        ("Claude",          {"fq": "model_mentions:claude"}),
        ("AI regulation",   {"fq": "source_dataset:reddit_ai_sentiment"}),
    ]
    for q, extra in spot_checks:
        label = f"{q} [{extra.get('fq', '')}]"
        try:
            count, latency = run_query(solr_url, q, extra)
            print(f"{label:<50} {count:>6} {latency:>10.2f}")
        except Exception as exc:
            print(f"{label:<50} ERROR: {exc}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark queries against Solr")
    parser.add_argument("--solr-url", default=DEFAULT_SOLR_URL)
    args = parser.parse_args()
    run_bench(args.solr_url)
