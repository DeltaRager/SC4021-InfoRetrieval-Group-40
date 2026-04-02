
## How to Run the Application

The application is split into two parts: the Solr backend (Search Engine Database) and the Vite frontend (User Interface). You will need to start both.

### 1. Start the Frontend UI (Required)

The UI is a lightweight web application built with Vanilla JS and served via Vite.

1. Open your terminal and navigate into the `ui` folder:
   ```bash
   cd ui
   ```
2. Start the Vite development server:
   ```bash
   npx vite
   ```
3. Open your browser and go to the local address provided (usually **http://localhost:5173**) to use the Search Engine interface!

### 2. Start the Apache Solr Backend
The backend utilizes Apache Solr running inside a Docker container.

**Start the Solr Engine:**
```bash
docker compose up -d
```
Solr will be available at [http://localhost:8983](http://localhost:8983). The `opinions_core` is created automatically on the first start.

**Stop the Solr Engine:**
```bash
docker compose down
```

**Stop and permanently remove all indexed data:**
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
│       └── reddit_data.csv      ← ACTIVE DATASET (swap this to change dataset, must be named reddit_data.csv)
│
├── sample_reddit_data.csv       ← Blueprint showing the required CSV column format
├── docker-compose.yml           ← Config to spin up Apache Solr locally
└── README.md                    
```

---

## Search Modes (to be done)

| Mode | How it works | Requires |
|---|---|---|
| **CSV Mode** (current) | Loads all rows into browser, uses substring matching | Just Vite |
| **Solr Mode** (future) | Sends query to Solr REST API, uses inverted index with BM25 ranking | Docker + Solr running |

Switching to Solr mode requires updating the `fetch` call in `main.js` from the CSV path to the Solr endpoint (`http://localhost:8983/solr/opinions_core/select`). 

---
