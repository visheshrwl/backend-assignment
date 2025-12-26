# Lyftr AI Backend Assignment

Containerized Webhook API built with FastAPI, SQLite, and Docker.

## Setup Used

VSCode + Gemini (Google Deepmind) + Copilot

## How to Run

### Prerequisites
- Docker & Docker Compose
- Make (optional, for shortcuts)

### commands

1. **Start the Stack**
   ```bash
   make up
   # OR
   docker compose up -d --build
   ```
   The API will be available at http://localhost:8000.

2. **Check Logs**
   ```bash
   make logs
   # OR
   docker compose logs -f api
   ```

3. **Shutdown**
   ```bash
   make down
   ```

4. **Run Tests**
   ```bash
   make test
   # OR
   pytest
   ```

## Endpoints

- `POST /webhook`: Ingest messages (requires HMAC `X-Signature`).
- `GET /messages`: List messages (pagination, filters).
- `GET /stats`: Analytics.
- `GET /health/live`, `/health/ready`: Probes.
- `GET /metrics`: Prometheus metrics.

## Design Decisions

### HMAC Verification
Implemented as a FastAPI dependency (`verify_signature`) to ensure it runs before the main handler but after basic request parsing. It re-computes the HMAC-SHA256 of the raw request body and uses `hmac.compare_digest` to prevent timing attacks.

### Pagination
Using standard `limit` and `offset` query parameters. Validation ensures `limit` is between 1 and 100 to prevent DOS.

### Logging
Used `python-json-logger` to format logs as structured JSON. A middleware captures request context (`request_id`, `latency_ms`, `status`) and ensures every request emits exactly one structured log line, plus application-specific logs for the webhook actions.
