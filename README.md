# SC4021-InfoRetrieval-Group-40

## Running Solr

**Start:**
```bash
docker compose up -d
```

Solr will be available at http://localhost:8983. The `opinions_core` is created automatically on first start.

**Stop:**
```bash
docker compose down
```

**Stop and remove all data:**
```bash
docker compose down -v
```
