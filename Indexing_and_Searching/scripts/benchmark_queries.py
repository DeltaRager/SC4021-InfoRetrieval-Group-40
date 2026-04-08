import argparse
import time

import requests

DEFAULT_SOLR_URL = "http://localhost:8983/solr/reddit_ai/select"
QUERIES = [
    "ChatGPT privacy",
    "Claude security",
    "AI agents risk",
    "prompt injection",
    "OpenAI regulation",
]


def run_bench(solr_url: str) -> None:
    print("Query\tResults\tLatency(ms)")
    for q in QUERIES:
        params = {
            "q": q,
            "defType": "edismax",
            "qf": "title^2 body full_text^3",
            "rows": 10,
            "wt": "json",
        }
        start = time.perf_counter()
        resp = requests.get(solr_url, params=params, timeout=15)
        resp.raise_for_status()
        latency = (time.perf_counter() - start) * 1000
        data = resp.json()
        count = data.get("response", {}).get("numFound", 0)
        print(f"{q}\t{count}\t{latency:.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark five fixed queries against Solr")
    parser.add_argument("--solr-url", default=DEFAULT_SOLR_URL)
    args = parser.parse_args()
    run_bench(args.solr_url)
