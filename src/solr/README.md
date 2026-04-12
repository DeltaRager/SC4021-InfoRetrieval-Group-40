# 3.2 Indexing (Solr)

This folder contains the Solr assets used by the canonical Flask search stack.

The root `docker-compose.yml` mounts `src/solr/configs/` into the Solr
container when it creates the `reddit_ai` core.

## 1) Start Solr

```bash
docker compose up -d
```

This repo standardizes the Flask search stack on the Solr core `reddit_ai`.

## 2) Create / update schema fields

```bash
curl -X POST -H "Content-type:application/json" http://localhost:8983/solr/reddit_ai/schema --data-binary "@schema_add_fields.json"
```

> If fields already exist, Solr may return an error; this is safe to ignore.

## 3) Install NLP dependencies + Build JSONL docs

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python scripts/prepare_solr_docs.py --output data/reddit_docs.jsonl
```

> The ETL script now runs spaCy lemmatization and YAKE concept extraction
> on each document, producing `lemmatized_text` and `concepts` fields.

```bash
python -c "import json; from pathlib import Path; p=Path(r'data\reddit_docs.jsonl'); docs=[json.loads(line) for line in p.open('r', encoding='utf-8') if line.strip()]; Path(r'data\reddit_docs.json').write_text(json.dumps(docs, ensure_ascii=False), encoding='utf-8')"
```

## 4) Index data into Solr
```bash
curl -X POST -H "Content-type:application/json" "http://localhost:8983/solr/reddit_ai/update?commit=true" --data-binary "@data\reddit_docs.json"
```

## 5) Run UI

```bash
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5001`.

## 6) Benchmark five required queries

```bash
python scripts/benchmark_queries.py
```
