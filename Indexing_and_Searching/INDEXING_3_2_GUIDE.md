# SC4021 — 3.2 Indexing Guide (AI Opinion Search Engine)

## Overview

This guide covers the full pipeline for indexing ~4.8k Reddit documents across four sources into a fielded BM25
Solr index optimised for opinion retrieval.

**Sources indexed:**
| File | Dataset label | Schema |
|---|---|---|
| `bitcoin_ai_posts_comments_5000pool.csv` | `bitcoin` | 3.1 CSV |
| `information_security_ai_posts_comments_5000pool.csv` | `information_security` | 3.1 CSV |
| `seo_ai_posts_comments_5000pool.csv` | `seo` | 3.1 CSV |
| `reddit_ai_sentiment_shortened.csv` | `reddit_ai_sentiment` | Sentiment CSV |

**Pipeline** (`scripts/prepare_solr_docs.py` + `nlp_utils.py`):
- Cleans text, removes duplicates, creates Solr-ready JSONL docs
- Enriches each document with sentiment label/score, model/vendor mentions, opinionatedness score
- **NLP enrichment** (when `nlp_utils` is available): generates `lemmatized_text` (spaCy lemmatization) and `concepts` (YAKE + spaCy noun chunks + NER)

---

## Step 1 — Start Solr

```bash
docker compose up -d
```

Solr UI: http://localhost:8983  
Core name: `reddit_ai`  *(created automatically from `docker-compose.yml`)*

If the collection was not pre-created, run:

```bash
docker exec -it sc4021-solr solr create_core -c reddit_ai
```

---

## Step 2 — Apply schema

```bash
curl -X POST -H 'Content-Type: application/json' \
  http://localhost:8983/solr/reddit_ai/schema \
  --data-binary @schema_add_fields.json
```

This adds all canonical opinion-search fields:
`type`, `title`, `body`, `search_text`, `lemmatized_text`, `concepts`, `subreddit`, `score`, `upvote_log`,
`created_date`, `time_bucket`, `source_dataset`, `source_schema`, `source_id`, `url`,
`model_mentions`, `vendor_mentions`, `sentiment_label`, `sentiment_score`, `opinionatedness_score`.

---

## Step 3 — Run the ingestion pipeline

```bash
cd Indexing_and_Searching
python scripts/prepare_solr_docs.py
```

The script auto-detects `reddit_ai_sentiment_shortened.csv` in common locations.
If it cannot find it, pass the path explicitly:

```bash
python scripts/prepare_solr_docs.py \
  --sentiment-file "/path/to/reddit_ai_sentiment_shortened.csv"
```

Output: `data/reddit_docs.jsonl` (one JSON document per line).

---

## Step 4 — Convert JSONL to JSON array

```bash
python - <<'EOF'
import json, pathlib
docs = [json.loads(l) for l in open("data/reddit_docs.jsonl")]
open("data/reddit_docs.json", "w").write(json.dumps(docs, ensure_ascii=False))
print(f"Converted {len(docs)} docs.")
EOF
```

---

## Step 5 — Index into Solr

```bash
curl -X POST \
  "http://localhost:8983/solr/reddit_ai/update?commit=true" \
  -H "Content-Type: application/json" \
  --data-binary @data/reddit_docs.json
```

Verify:

```bash
curl "http://localhost:8983/solr/reddit_ai/select?q=*:*&rows=0&wt=json" | python -m json.tool | grep numFound
```

---

## Step 6 — Start the embedding and reranker models

The hybrid retrieval pipeline requires two local model servers powered by **llama.cpp**.

### Install llama.cpp

Follow the official instructions at https://github.com/ggerganov/llama.cpp to build or install `llama-server` for your platform.

### Download the models

| Model | Source |
|---|---|
| `jina-embeddings-v3-f16.gguf` | https://huggingface.co/gaianet/jina-embeddings-v3-GGUF |
| `bge-reranker-v2-m3-FP16.gguf` | https://huggingface.co/gpustack/bge-reranker-v2-m3-GGUF |

Place both `.gguf` files under `~/Desktop/Models/` (or adjust the paths in the commands below).

### Start the embedding server (port 8081)

```bash
llama-server -m ~/Desktop/Models/jina-embeddings-v3-f16.gguf --embeddings --port 8081 -c 8192
```

### Start the reranker server (port 8082)

```bash
llama-server -m ~/Desktop/Models/bge-reranker-v2-m3-FP16.gguf --rerank --port 8082 -c 8192
```

Keep both servers running in separate terminals before starting the Flask app. The app calls:
- `http://localhost:8081/v1/embeddings` for dense vector search
- `http://localhost:8082/v1/rerank` for cross-encoder reranking

---

## Step 7 — Run the Flask UI

```bash
cd Indexing_and_Searching
pip install -r requirements.txt
python app.py
```

Open http://localhost:5001

The Flask app defaults to `http://localhost:8983/solr/reddit_ai/select`. If you override
`SOLR_URL`, point it at a core with the full `schema_add_fields.json` schema. On startup/query,
the app now checks that the target core exists and contains the required fields used by the
search UI.

### Filters available in the UI
- **Type**: post / comment / unknown
- **Sentiment**: positive / negative / neutral / mixed
- **Dataset**: bitcoin / information_security / seo / reddit_ai_sentiment
- **AI Model**: chatgpt / claude / gemini / llama / copilot / mistral / grok / deepseek / perplexity
- **Subreddit**: free text
- **Date range**: from / to
- **Sort**: Top score / Newest

### Facets displayed in the sidebar
Sentiment, Dataset, AI Model, Subreddit, Type — all clickable to drill down.

---

## Step 8 — Run benchmarks

```bash
cd Indexing_and_Searching
python scripts/benchmark_queries.py
```

Prints result count and latency for:
- 5 baseline queries (original 3.2 requirements)
- 5 opinion-specific queries
- 3 facet/filter spot checks

---

## Solr query profile

| Parameter | Value |
|---|---|
| `defType` | `edismax` |
| `qf` | `title^4 search_text^3 body^1.5` (+ `lemmatized_text^2.5 concepts^2` when NLP on) |
| `pf` | `title^8 search_text^4` (+ `lemmatized_text^3` when NLP on) |
| `mm` | `2<75%` |
| `boost` | `product(upvote_log, 0.1)` |
| `bq` (NLP on) | lemmatized query^2, concept phrases^1.5, fuzzy fallback^1.2 |
| Highlighting | `search_text`, `body`, `title`, `lemmatized_text`, `concepts` |

---

## Field reference

| Field | Type | Notes |
|---|---|---|
| `id` | string | SHA1 or stable Reddit ID |
| `source_id` | string | Original Reddit ID (sentiment file only) |
| `source_dataset` | string | bitcoin / information_security / seo / reddit_ai_sentiment |
| `source_schema` | string | 3.1_csv / sentiment_csv |
| `type` | string | post / comment / unknown |
| `title` | text_en | First 150 chars for posts |
| `body` | text_en | Full text |
| `search_text` | text_en | Combined retrieval field |
| `lemmatized_text` | text_en | spaCy-lemmatized form for morphological recall |
| `concepts` | text_en | YAKE + noun chunks + NER keyphrases |
| `subreddit` | string (exact) | Facet-ready |
| `score` | pint | Raw upvote count |
| `upvote_log` | pfloat | log(score+1) for boost |
| `created_date` | pdate | ISO-8601 UTC |
| `time_bucket` | string | recent_week / recent_month / recent_quarter / older |
| `url` | string | Reddit URL when available |
| `model_mentions` | string[] | chatgpt / claude / gemini / llama / … |
| `vendor_mentions` | string[] | openai / anthropic / google / meta / … |
| `sentiment_label` | string | positive / negative / neutral / mixed |
| `sentiment_score` | pfloat | [-1.0, 1.0] |
| `opinionatedness_score` | pfloat | [0.0, 1.0] |

---

## Assignment writeup mapping

| Assignment section | Evidence |
|---|---|
| Indexing + schema | Step 2 (`schema_add_fields.json`) + `managed-schema.xml` |
| Five benchmark queries | Step 7 output table |
| UI + filters | Step 6 screenshot (type, sentiment, model, dataset, subreddit, date) |
| Speed | Benchmark latency column |
| Innovation | Sentiment/opinion fields, model/vendor facets, eDisMax + phrase boost, `time_bucket` |
