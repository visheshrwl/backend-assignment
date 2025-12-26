from prometheus_client import Counter

# Metrics
# Metrics
# HTTP metrics are now handled by prometheus-fastapi-instrumentator

WEBHOOK_REQUESTS_TOTAL = Counter(
    "webhook_requests_total",
    "Processing outcomes for webhook requests",
    ["result"]
)
