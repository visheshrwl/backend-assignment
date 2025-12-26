# Lyftr AI Backend Assignment

A production-ready, containerized webhook API built with **Python 3.11**, **FastAPI**, and **SQLite**. This project adheres to 12-factor principles and includes features like Prometheus/Grafana observability, rate limiting, and strict CI/CD.

## Tech Stack
*   **Framework**: FastAPI (Async)
*   **Database**: SQLite (via `aiosqlite` + `SQLAlchemy`)
*   **Containerization**: Docker & Docker Compose
*   **Observability**: Prometheus & Grafana
*   **Testing**: Pytest (Asyncio)

## Quick Start

### Prerequisites
*   Docker & Docker Compose
*   Make (optional)

### Running the Stack
1.  **Start Services**:
    ```bash
    make up
    # OR: docker compose up -d --build
    ```
    This spins up three containers:
    *   `api`: The application (Port 8000)
    *   `prometheus`: Metrics scraper (Port 9090)
    *   `grafana`: Dashboards (Port 3000)

2.  **Verify Status**:
    ```bash
    curl http://localhost:8000/health/live
    # {"status":"ok"}
    ```

3.  **Shutdown**:
    ```bash
    make down
    ```

## Configuration
The application is configured via Environment Variables (defined in `docker-compose.yml` or `.env`):

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite+aiosqlite:////data/app.db` |
| `WEBHOOK_SECRET` | Secret for HMAC signature validation | `testsecret` |
| `LOG_LEVEL` | Logging level (`INFO`, `DEBUG`) | `INFO` |

## API Documentation

### `POST /webhook`
Ingests messages with HMAC verification and idempotency.
*   **Headers**: `X-Signature` (HMAC-SHA256 of body using `WEBHOOK_SECRET`).
*   **Rate Limit**: 60 req/min.
*   **Responses**:
    *   `200 OK`: Message accepted (created or duplicate).
    *   `401 Unauthorized`: Invalid/Missing signature.
    *   `422 Unprocessable Entity`: Invalid JSON payload.
    *   `429 Too Many Requests`: Rate limit exceeded.

### `GET /messages`
List messages with pagination and filtering.
*   **Params**:
    *   `limit` (1-100), `offset` (0+).
    *   `from` (filter by sender).
    *   `since` (ISO-8601 timestamp).
    *   `q` (Text search).

### `GET /stats`
Returns analytical data:
*   Total message count.
*   Unique sender count.
*   Top 10 senders by volume.
*   First/Last message timestamps.

### `GET /metrics`
Prometheus endpoints exposing:
*   `http_requests_total`: Counter by `path`, `method`, `status`.
*   `webhook_requests_total`: Counter by `result` (`created`, `duplicate`, `invalid_signature`).
*   `http_request_duration_seconds`: Histogram of latency.

### `GET /health/live` & `/health/ready`
Liveness and Readiness probes for Kubernetes/Docker.

## Observability & Quality

### Grafana Dashboard
Access Grafana at **http://localhost:3000** (User: `admin`, Pass: `admin`).
A pre-provisioned **"Backend Dashboard"** is available, visualizing:
*   Request Rate (RPM)
*   p95 & p99 Latency
*   Webhook Outcomes & Error Rates

### Logging
Logs are emitted as **Structured JSON** for easy parsing (e.g., by Datadog/Splunk).
```json
{"ts": "2025-01-01T10:00:00Z", "level": "INFO", "request_id": "...", "method": "POST", "path": "/webhook", "status": 200, "latency_ms": 12.5, "message_id": "m1", "result": "created"}
```

### Development
Run tests and static analysis:
```bash
# Run Unit Tests
make test
# OR: docker compose run --rm api pytest

# Run Linting (Ruff & Mypy)
docker compose run --rm api sh -c "ruff check . && mypy ."
```
