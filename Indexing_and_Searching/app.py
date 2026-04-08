import os
import time
from typing import Any

import requests
from flask import Flask, render_template, request

app = Flask(__name__)

SOLR_URL = os.getenv("SOLR_URL", "http://localhost:8983/solr/reddit_ai/select")
DEFAULT_ROWS = 20


@app.get("/")
def index() -> str:
    q = request.args.get("q", "").strip()
    doc_type = request.args.get("type", "")
    subreddit = request.args.get("subreddit", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    sort = request.args.get("sort", "score desc")

    results: list[dict[str, Any]] = []
    response_ms = None
    num_found = 0
    facets: dict[str, Any] = {}
    error = ""

    if q:
        fq = []
        if doc_type:
            fq.append(f"type:{doc_type}")
        if subreddit:
            fq.append(f"subreddit:{subreddit}")
        if date_from or date_to:
            date_from_safe = date_from + "T00:00:00Z" if date_from else "*"
            date_to_safe = date_to + "T23:59:59Z" if date_to else "*"
            fq.append(f"created_date:[{date_from_safe} TO {date_to_safe}]")

        params = {
            "q": q,
            "defType": "edismax",
            "qf": "title^2 body full_text^3",
            "fl": "id,type,title,body,subreddit,score,created_date,thread_id",
            "rows": DEFAULT_ROWS,
            "start": 0,
            "wt": "json",
            "hl": "true",
            "hl.fl": "title,body,full_text",
            "hl.simple.pre": "<mark>",
            "hl.simple.post": "</mark>",
            "facet": "true",
            "facet.field": ["type", "subreddit"],
            "sort": sort,
        }
        if fq:
            params["fq"] = fq

        start = time.perf_counter()
        try:
            resp = requests.get(SOLR_URL, params=params, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            elapsed = (time.perf_counter() - start) * 1000
            response_ms = round(elapsed, 2)

            docs = payload.get("response", {}).get("docs", [])
            num_found = payload.get("response", {}).get("numFound", 0)
            highlighting = payload.get("highlighting", {})

            for doc in docs:
                hl = highlighting.get(doc["id"], {})
                snippet = ""
                for field in ("full_text", "body", "title"):
                    if hl.get(field):
                        snippet = hl[field][0]
                        break
                if not snippet:
                    snippet = (doc.get("body") or doc.get("title") or "")[:260]

                results.append(
                    {
                        **doc,
                        "snippet": snippet,
                    }
                )

            facets = payload.get("facet_counts", {}).get("facet_fields", {})
        except requests.RequestException as exc:
            error = f"Failed to query Solr: {exc}"

    return render_template(
        "index.html",
        q=q,
        doc_type=doc_type,
        subreddit=subreddit,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        results=results,
        response_ms=response_ms,
        num_found=num_found,
        facets=facets,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
