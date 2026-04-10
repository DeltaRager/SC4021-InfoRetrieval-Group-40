# SC4021 - 3.2 Indexing Delivery Guide

This repository now includes a **minimum viable 3.2 implementation** based on your 3.1 Reddit crawling CSV files.

## Included components

1. **Indexing pipeline** (`scripts/prepare_solr_docs.py` + `nlp_utils.py`)
   - Reads 3 CSV files from 3.1
   - Cleans text, removes duplicates, creates Solr-ready JSONL docs
   - Builds fields required for retrieval: `id`, `type`, `title`, `body`, `full_text`, `subreddit`, `score`, `created_date`, `thread_id`
   - **NLP enrichment**: generates `lemmatized_text` (spaCy lemmatization) and `concepts` (YAKE + spaCy noun chunks + NER) for each document

2. **Simple query UI** (`app.py` + `templates/index.html`)
   - Search box
   - Filters: `type`, `subreddit`, `date range`
   - Sort: score / newest
   - Highlights matched terms
   - Shows response time in milliseconds

3. **Five-query speed test** (`scripts/benchmark_queries.py`)
   - Runs 5 representative queries required by the assignment
   - Prints result count and latency

4. **Solr setup instructions** (`solr/README.md`)
   - Docker startup
   - Schema creation
   - Data indexing

## Suggested writeup mapping to assignment

- **Q2 (Indexing + UI + five queries + speed):**
  - Use `solr/README.md` commands and UI screenshots.
- **Q3 (Innovation):**
  - Timeline filtering (`date_from`, `date_to`)
  - Faceted search (`type`, `subreddit` facets)
  - Highlight snippets (`hl=true` in Solr query)
  - **Lemmatization** (`nlp_utils.py`): spaCy-based POS-aware lemmatization applied at both index time and query time. Reduces morphological variants to dictionary forms (e.g., "running" -> "run", "bought" -> "buy") so that queries like "artificially intelligent" can match documents about "artificial intelligence".
  - **Concept Extraction** (`nlp_utils.py`): Combines YAKE keyphrase extraction with spaCy noun chunks and named entity recognition to extract multi-word concepts. Enables semantic-level matching beyond individual keywords.
  - **Smart Stopword Removal**: Removes common stopwords while preserving them inside meaningful phrases detected via noun chunks and named entities (e.g., "King of Denmark", "flights to London").
  - **Boost queries**: Lemmatized and concept fields are used as Solr boost queries (`bq`) to improve ranking without excluding results.

