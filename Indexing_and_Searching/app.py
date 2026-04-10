import logging
import math
import os
import time
from typing import Any

import requests
from flask import Flask, render_template, request

from nlp_utils import process_query

app = Flask(__name__)
logger = logging.getLogger(__name__)

SOLR_URL = os.getenv("SOLR_URL", "http://localhost:8983/solr/reddit_ai/select")
DEFAULT_ROWS = 20


def _build_fq(doc_type, subreddit, date_from, date_to,
              sentiment, source_dataset, model, vendor):
    fq = []
    if doc_type:
        fq.append(f"type:{doc_type}")
    if subreddit:
        fq.append(f"subreddit:{subreddit}")
    if date_from or date_to:
        d_from = (date_from + "T00:00:00Z") if date_from else "*"
        d_to   = (date_to   + "T23:59:59Z") if date_to   else "*"
        fq.append(f"created_date:[{d_from} TO {d_to}]")
    if sentiment:
        fq.append(f"sentiment_label:{sentiment}")
    if source_dataset:
        fq.append(f"source_dataset:{source_dataset}")
    if model:
        fq.append(f"model_mentions:{model}")
    if vendor:
        fq.append(f"vendor_mentions:{vendor}")
    return fq


def _popularity_boost(score_str: str) -> float:
    """log(score+1) capped at 10 for bq boost."""
    try:
        return round(min(math.log1p(max(int(score_str), 0)), 10), 2)
    except Exception:
        return 0.0


@app.get("/")
def index() -> str:
    q              = request.args.get("q", "").strip()
    doc_type       = request.args.get("type", "")
    subreddit      = request.args.get("subreddit", "")
    date_from      = request.args.get("date_from", "")
    date_to        = request.args.get("date_to", "")
    sort           = request.args.get("sort", "score desc")
    sentiment      = request.args.get("sentiment", "")
    source_dataset = request.args.get("source_dataset", "")
    model          = request.args.get("model", "")
    vendor         = request.args.get("vendor", "")
    # Toggle: enable/disable NLP enhancement (on by default).
    # The HTML form sends both a hidden input (value="0") and a checkbox
    # (value="1"), so when checked the URL contains nlp=0&nlp=1.
    # Flask's request.args.get() returns only the first value ("0"),
    # so we must check if "1" appears anywhere in the value list.
    use_nlp = "1" in request.args.getlist("nlp") if request.args.getlist("nlp") else True

    results: list[dict[str, Any]] = []
    response_ms = None
    num_found = 0
    facets: dict[str, Any] = {}
    error = ""
    nlp_info: dict[str, Any] = {}

    if q:
        # ---- NLP query enhancement ----
        # Always keep the original query as primary -- Solr's text_en
        # field type already handles tokenisation and Porter stemming.
        # NLP enrichment adds lemmatized + concept boost queries to
        # improve recall for morphological variants and multi-word
        # concepts without risking stopword loss in phrases like
        # "King of Denmark" or "flights to London".
        solr_q = q
        if use_nlp:
            try:
                nlp_result = process_query(q)
                nlp_info = nlp_result

                # Always use the fully processed query (after prefix
                # completion, wildcard expansion, and spell correction).
                # No "Did you mean" prompt -- auto-correct directly.
                solr_q = nlp_result.get("final_query", q)
            except Exception as exc:
                logger.warning("NLP processing failed, falling back to raw query: %s", exc)
                nlp_info = {}
                error = f"NLP enhancement failed ({type(exc).__name__}: {exc}). Falling back to basic search."

        fq = _build_fq(doc_type, subreddit, date_from, date_to,
                       sentiment, source_dataset, model, vendor)

        # Build query-field weights:
        #   - search_text for combined retrieval
        #   - lemmatized_text for morphological recall (lemma matching)
        #   - concepts for semantic/keyphrase matching
        qf = "title^4 search_text^3 body^1.5"
        pf = "title^8 search_text^4"
        if use_nlp:
            qf = "title^4 search_text^3 body^1.5 lemmatized_text^2.5 concepts^2"
            pf = "title^8 search_text^4 lemmatized_text^3"

        params: dict[str, Any] = {
            "q":       solr_q,
            "defType": "edismax",
            "qf":      qf,
            "pf":      pf,
            "mm":      "2<75%",
            "fl":      ("id,type,title,body,subreddit,score,created_date,"
                        "source_dataset,sentiment_label,sentiment_score,"
                        "model_mentions,vendor_mentions,opinionatedness_score"),
            "rows":    DEFAULT_ROWS,
            "start":   0,
            "wt":      "json",
            "hl":      "true",
            "hl.fl":   "search_text,body,title,lemmatized_text,concepts",
            "hl.simple.pre":  "<mark>",
            "hl.simple.post": "</mark>",
            "facet":   "true",
            "facet.field": [
                "type", "subreddit", "sentiment_label",
                "source_dataset", "model_mentions", "vendor_mentions",
            ],
            "sort":  sort,
            # mild popularity boost via function query
            "boost": "product(upvote_log,0.1)",
        }

        # Build boost queries (bq) -- these only affect ranking, never
        # exclude documents.  We layer multiple signals:
        #   1. Lemmatized query  → rewards morphological matches
        #   2. Concept phrases   → rewards semantic matches
        #   3. Fuzzy original    → catches residual typos that spell-
        #                          correction missed (domain jargon etc.)
        if use_nlp and nlp_info:
            bq_parts: list[str] = []

            lemmatized_q = nlp_info.get("lemmatized", "")
            if lemmatized_q and lemmatized_q.lower() != solr_q.lower():
                bq_parts.append(f'lemmatized_text:({lemmatized_q})^2')

            query_concepts = nlp_info.get("concepts", [])
            if query_concepts:
                concept_boost = " OR ".join(
                    f'"{c}"' for c in query_concepts[:5]
                )
                bq_parts.append(f"concepts:({concept_boost})^1.5")

            # Fuzzy boost: use the ORIGINAL (possibly misspelled) query
            # with ~N operators so Solr's Levenshtein automata can still
            # match even if pyspellchecker didn't know the correct word.
            fuzzy_q = nlp_info.get("fuzzy", "")
            if fuzzy_q and fuzzy_q != solr_q:
                bq_parts.append(f"search_text:({fuzzy_q})^1.2")

            if bq_parts:
                params["bq"] = bq_parts

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
                for field_name in ("search_text", "body", "title", "lemmatized_text", "concepts"):
                    if hl.get(field_name):
                        snippet = hl[field_name][0]
                        break
                if not snippet:
                    snippet = (doc.get("body") or doc.get("title") or "")[:260]

                results.append({**doc, "snippet": snippet})

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
        sentiment=sentiment,
        source_dataset=source_dataset,
        model=model,
        vendor=vendor,
        use_nlp=use_nlp,
        results=results,
        response_ms=response_ms,
        num_found=num_found,
        facets=facets,
        nlp_info=nlp_info,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
