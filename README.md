
## How to Run the Application

The application is split into two parts: the Solr backend (Search Engine Database) and the Vite frontend (User Interface). You will need to start both.

### 1. Start the Frontend UI (Localhost Website)
The UI is a modern, lightweight web application built with Vanilla JavaScript and served via Vite.

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

## Project Architecture
* **`ui/`**: Contains the frontend Search Engine UI code (`index.html`, `main.js`, `style.css`).
* **`docker-compose.yml`**: Configuration for spinning up the Apache Solr server locally.
* **`sample_reddit_data.csv`**: A blueprint showing how our cleaned datasets are formatted prior to being ingested by Solr.
