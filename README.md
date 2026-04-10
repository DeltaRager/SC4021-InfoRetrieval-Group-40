
## How to Run the Application

This repo currently contains two different UI paths:

- `Indexing_and_Searching/` is the canonical Solr-backed Flask search application. It expects the Solr core `reddit_ai`.
- `ui/` is a separate Vite demo that currently runs in CSV mode and does not drive the Flask/Solr search stack directly.

If you want the full Solr-backed search engine, use the Flask path below.

## Canonical Solr-Backed Search Stack

The Flask application and Solr backend must both be running.

### 1. Start Apache Solr

```bash
docker compose up -d
```

Solr will be available at [http://localhost:8983](http://localhost:8983). The `reddit_ai` core is created automatically on the first start.

### 2. Apply the Search Schema

```bash
cd Indexing_and_Searching
curl -X POST -H "Content-type:application/json" \
  http://localhost:8983/solr/reddit_ai/schema \
  --data-binary "@schema_add_fields.json"
```

### 3. Run the Flask Search App

```bash
cd Indexing_and_Searching
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5001](http://localhost:5001).

The Flask app defaults to `http://localhost:8983/solr/reddit_ai/select`. Override this with `SOLR_URL` only if you intentionally use a different Solr core.

### Solr Maintenance

Stop the Solr service:

```bash
docker compose down
```

Stop Solr and permanently remove indexed data:

```bash
docker compose down -v
```

---

## Project File Map

```
SC4021-InfoRetrieval-Group-40/
│
├── ui/                          ← Frontend website (entry point)
│   ├── index.html               ← Page structure (search bar, buttons, layout)
│   ├── main.js                  ← Search logic, data loading, card rendering
│   ├── style.css                ← All visual design and animations
│   └── public/
│       └── reddit_data.csv      ← CSV dataset for the standalone Vite demo
│
├── Indexing_and_Searching/      ← Canonical Flask + Solr opinion-search stack
├── sample_reddit_data.csv       ← Blueprint showing the required CSV column format
├── docker-compose.yml           ← Config to spin up Apache Solr locally (`reddit_ai`)
└── README.md                    
```

---

## Vite Demo Path

| Mode | How it works | Requires |
|---|---|---|
| **CSV Mode** (current) | Loads all rows into browser, uses substring matching | Just Vite |
| **Flask + Solr Mode** | Uses the `Indexing_and_Searching/` app with Apache Solr and BM25-style ranking | Docker + Flask |

To run the standalone Vite demo:

```bash
cd ui
npx vite
```

Open the local address printed by Vite, usually [http://localhost:5173](http://localhost:5173).

The Vite demo should be treated as CSV-only unless it is explicitly reworked to call the Flask/Solr search backend.

---
