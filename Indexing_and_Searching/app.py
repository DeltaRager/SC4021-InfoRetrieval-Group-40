import logging
import math
import os
import re
import time
from urllib.parse import urlparse
from typing import Any

import requests
from flask import Flask, render_template, request

from nlp_utils import process_query
from hybrid_search import (
    EmbeddingClient,
    RerankerClient,
    HybridSearchService,
    RetrievalInfo,
    SEARCH_ROWS,
)

app = Flask(__name__)
logger = logging.getLogger(__name__)

SOLR_URL = os.getenv("SOLR_URL", "http://localhost:8983/solr/reddit_ai/select")
DEFAULT_ROWS = SEARCH_ROWS
REQUIRED_SOLR_FIELDS = {
    "title",
    "body",
    "search_text",
    "lemmatized_text",
    "concepts",
    "upvote_log",
    "created_date",
    "model_mentions",
    "vendor_mentions",
}
SAFE_TERM_RE = re.compile(r"^[\w*~.-]+$", re.ASCII)

# Module-level service singletons (created once at import time).
_embedder = EmbeddingClient()
_reranker = RerankerClient()
_hybrid   = HybridSearchService(SOLR_URL, _embedder, _reranker)


def _build_fq(doc_type, subreddit, date_from, date_to,
              polarity, subjectivity, source_dataset, model, vendor):
    fq = []
    if doc_type:
        fq.append(f"type:{doc_type}")
    if subreddit:
        fq.append(f"subreddit:{subreddit}")
    if date_from or date_to:
        d_from = (date_from + "T00:00:00Z") if date_from else "*"
        d_to   = (date_to   + "T23:59:59Z") if date_to   else "*"
        fq.append(f"created_date:[{d_from} TO {d_to}]")
    if polarity:
        fq.append(f"polarity_label:{polarity}")
    if subjectivity:
        fq.append(f"subjectivity_label:{subjectivity}")
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


def _solr_core_context(solr_url: str) -> tuple[str, str]:
    parsed = urlparse(solr_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2 or path_parts[0] != "solr":
        raise ValueError(
            "SOLR_URL must look like http://host:8983/solr/<core>/select"
        )
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return base_url, path_parts[1]


def _solr_setup_status(solr_url: str) -> tuple[bool, str]:
    base_url, core_name = _solr_core_context(solr_url)

    try:
        cores_resp = requests.get(
            f"{base_url}/solr/admin/cores",
            params={"action": "STATUS", "wt": "json"},
            timeout=5,
        )
        cores_resp.raise_for_status()
        core_status = cores_resp.json().get("status", {})
    except requests.RequestException as exc:
        logger.warning("Solr setup check failed while querying cores: %s", exc)
        return False, (
            f"Could not reach Solr at {base_url}. Start the local Solr service and ensure "
            f"`SOLR_URL` points to the Flask search core (`reddit_ai`)."
        )

    if core_name not in core_status:
        return False, (
            f"Solr core `{core_name}` is missing. The Flask search stack expects the "
            f"`reddit_ai` core. Start Solr with that core or override `SOLR_URL`."
        )

    try:
        schema_resp = requests.get(
            f"{base_url}/solr/{core_name}/schema/fields",
            params={"wt": "json"},
            timeout=5,
        )
        schema_resp.raise_for_status()
        schema_fields = {
            field.get("name", "")
            for field in schema_resp.json().get("fields", [])
            if field.get("name")
        }
    except requests.RequestException as exc:
        logger.warning("Solr setup check failed while querying schema: %s", exc)
        return False, (
            f"Could not inspect the schema for Solr core `{core_name}`. Apply "
            "`schema_add_fields.json` before running the Flask search app."
        )

    missing_fields = sorted(REQUIRED_SOLR_FIELDS - schema_fields)
    if missing_fields:
        missing = ", ".join(missing_fields)
        return False, (
            f"Solr core `{core_name}` is missing required schema fields: {missing}. "
            "Apply `Indexing_and_Searching/schema_add_fields.json` and reindex the data."
        )

    return True, ""


def _get_solr_setup_error(solr_url: str) -> str:
    try:
        ok, message = _solr_setup_status(solr_url)
        return "" if ok else message
    except ValueError as exc:
        logger.warning("Invalid SOLR_URL: %s", exc)
        return str(exc)


def _escape_solr_phrase(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_lemmatized_boost(lemmatized_q: str, solr_q: str) -> str | None:
    if not lemmatized_q or lemmatized_q.lower() == solr_q.lower():
        return None
    tokens = [token for token in lemmatized_q.split() if SAFE_TERM_RE.fullmatch(token)]
    if not tokens:
        return None
    return f"lemmatized_text:({' '.join(tokens)})^2"


def _build_concept_boost(query_concepts: list[str]) -> str | None:
    safe_phrases = []
    for concept in query_concepts[:5]:
        cleaned = " ".join(concept.split()).strip()
        if not cleaned:
            continue
        if any(ch in cleaned for ch in "()[]{}:"):
            continue
        safe_phrases.append(f'"{_escape_solr_phrase(cleaned)}"')
    if not safe_phrases:
        return None
    return f"concepts:({' OR '.join(safe_phrases)})^1.5"


def _build_fuzzy_boost(fuzzy_q: str, solr_q: str) -> str | None:
    if not fuzzy_q or fuzzy_q == solr_q:
        return None
    tokens = [token for token in fuzzy_q.split() if SAFE_TERM_RE.fullmatch(token)]
    if not tokens:
        return None
    return f"search_text:({' '.join(tokens)})^1.2"


def _log_solr_error(resp: requests.Response, params: dict[str, Any]) -> None:
    flattened_params: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, list):
            flattened_params[key] = value
        else:
            flattened_params[key] = str(value)
    logger.error(
        "Solr request failed: status=%s url=%s params=%s body=%s",
        resp.status_code,
        resp.url,
        flattened_params,
        resp.text[:1500],
    )


@app.get("/")
def index() -> str:
    q              = request.args.get("q", "").strip()
    doc_type       = request.args.get("type", "")
    subreddit      = request.args.get("subreddit", "")
    date_from      = request.args.get("date_from", "")
    date_to        = request.args.get("date_to", "")
    sort           = request.args.get("sort", "score desc")
    polarity       = request.args.get("polarity", "")
    subjectivity   = request.args.get("subjectivity", "")
    source_dataset = request.args.get("source_dataset", "")
    model          = request.args.get("model", "")
    vendor         = request.args.get("vendor", "")
    # Toggle: enable/disable NLP enhancement (on by default).
    # The HTML form sends both a hidden input (value="0") and a checkbox
    # (value="1"), so when checked the URL contains nlp=0&nlp=1.
    # Flask's request.args.get() returns only the first value ("0"),
    # so we must check if "1" appears anywhere in the value list.
    use_nlp = "1" in request.args.getlist("nlp") if request.args.getlist("nlp") else True
    use_vector = "1" in request.args.getlist("vector") if request.args.getlist("vector") else True

    results: list[dict[str, Any]] = []
    response_ms = None
    num_found = 0
    facets: dict[str, Any] = {}
    error = ""
    nlp_info: dict[str, Any] = {}
    retrieval_info: dict[str, Any] = {}

    if q:
        setup_error = _get_solr_setup_error(SOLR_URL)
        if setup_error:
            error = setup_error
            return render_template(
                "index.html",
                q=q,
                doc_type=doc_type,
                subreddit=subreddit,
                date_from=date_from,
                date_to=date_to,
                sort=sort,
                polarity=polarity,
                subjectivity=subjectivity,
                source_dataset=source_dataset,
                model=model,
                vendor=vendor,
                use_nlp=use_nlp,
                use_vector=use_vector,
                results=results,
                response_ms=response_ms,
                num_found=num_found,
                facets=facets,
                nlp_info=nlp_info,
                retrieval_info=retrieval_info,
                error=error,
            )

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
                       polarity, subjectivity, source_dataset, model, vendor)

        # Build query-field weights:
        #   - search_text for combined retrieval
        #   - lemmatized_text for morphological recall (lemma matching)
        #   - concepts for semantic/keyphrase matching
        qf = "title^4 search_text^3 body^1.5"
        pf = "title^8 search_text^4"
        if use_nlp:
            qf = "title^4 search_text^3 body^1.5 lemmatized_text^2.5 concepts^2"
            pf = "title^8 search_text^4 lemmatized_text^3"

        # Build boost queries (bq) -- these only affect ranking, never
        # exclude documents.  We layer multiple signals:
        #   1. Lemmatized query  → rewards morphological matches
        #   2. Concept phrases   → rewards semantic matches
        #   3. Fuzzy original    → catches residual typos that spell-
        #                          correction missed (domain jargon etc.)
        bq_parts: list[str] = []
        if use_nlp and nlp_info:
            lemmatized_bq = _build_lemmatized_boost(nlp_info.get("lemmatized", ""), solr_q)
            if lemmatized_bq:
                bq_parts.append(lemmatized_bq)

            concept_bq = _build_concept_boost(nlp_info.get("concepts", []))
            if concept_bq:
                bq_parts.append(concept_bq)

            # Fuzzy boost: use the ORIGINAL (possibly misspelled) query
            # with ~N operators so Solr's Levenshtein automata can still
            # match even if pyspellchecker didn't know the correct word.
            fuzzy_bq = _build_fuzzy_boost(nlp_info.get("fuzzy", ""), solr_q)
            if fuzzy_bq:
                bq_parts.append(fuzzy_bq)

        # ---- Hybrid retrieval pipeline ----
        # Build concept_text for dual-path vector embedding (channel b = f(b)).
        concept_text = nlp_info.get("concept_text", "") if use_nlp and nlp_info else ""

        start = time.perf_counter()
        try:
            results, facets, num_found, info = _hybrid.search(
                solr_q=solr_q,
                fq=fq,
                qf=qf,
                pf=pf,
                bq=bq_parts,
                sort=sort,
                use_nlp=use_nlp,
                query_text=q,  # use original query for semantic embedding
                use_vector=use_vector,
                concept_text=concept_text,
            )
            elapsed = (time.perf_counter() - start) * 1000
            response_ms = round(elapsed, 2)
            retrieval_info = info.as_dict()
            # num_found from lexical retrieval reflects the candidate pool size,
            # not the number of results shown (pipeline caps at SEARCH_ROWS=20).
            num_found = len(results)

            # Surface any degradation warnings as the existing error banner
            if info.degraded and info.warnings:
                warn_text = " ".join(info.warnings)
                if error:
                    error = error + " " + warn_text
                else:
                    error = warn_text

        except requests.HTTPError as exc:
            response = exc.response
            if response is not None:
                _log_solr_error(response, {"q": solr_q, "fq": fq})
                error = (
                    "Solr rejected the query. Check the Flask search core schema and "
                    "server logs for the exact invalid parameter."
                )
            else:
                error = f"Failed to query Solr: {exc}"
        except requests.RequestException as exc:
            logger.warning("Solr request failed: %s", exc)
            error = (
                "Could not reach Solr while running the search. Ensure the Solr service "
                "is running and that `SOLR_URL` points to the `reddit_ai` core."
            )

    return render_template(
        "index.html",
        q=q,
        doc_type=doc_type,
        subreddit=subreddit,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        polarity=polarity,
        subjectivity=subjectivity,
        source_dataset=source_dataset,
        model=model,
        vendor=vendor,
        use_nlp=use_nlp,
        use_vector=use_vector,
        results=results,
        response_ms=response_ms,
        num_found=num_found,
        facets=facets,
        nlp_info=nlp_info,
        retrieval_info=retrieval_info,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
