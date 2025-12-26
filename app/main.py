import hashlib
import hmac
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import metrics as prometheus_metrics
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.logging_utils import logger
from app.metrics import WEBHOOK_REQUESTS_TOTAL
from app.models import Message, MessageResponse, WebhookPayload
from app.storage import get_db, init_db, insert_message

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler) # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)


# --- Security Middlewares ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# --- Instrumentator ---
instrumentator = Instrumentator()
instrumentator.add(
    prometheus_metrics.requests(
        metric_name="http_requests_total",
        should_include_handler=True,
        should_include_method=True,
        should_include_status=True
    )
)
instrumentator.instrument(app).expose(app)




# --- Middleware ---

@app.middleware("http")
async def log_and_metrics_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Context for logging
    log_context: dict[str, Any] = {
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
    }
    
    response = None
    status_code = 500
    
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        # FastAPI handles exceptions, but we capture 500s here if unhandled
        logger.error(f"Unhandled exception: {e}", extra=log_context)
        raise e
    finally:
        latency = (time.time() - start_time) * 1000
        log_context["latency_ms"] = latency
        log_context["status"] = status_code
        
        # Update Metrics
        # HTTP_REQUESTS_TOTAL.labels(path=request.url.path, status=str(status_code)).inc()
        # REQUEST_LATENCY_MS.observe(latency)

        
        # Log
        logger.info("Request processed", extra=log_context)
        
    return response

# --- Dependencies ---

async def verify_signature(request: Request, x_signature: str = Header(None)):
    if not settings.WEBHOOK_SECRET:
        logger.error("WEBHOOK_SECRET not set")
        raise HTTPException(status_code=503, detail="Service not configured")

    if not x_signature:
        WEBHOOK_REQUESTS_TOTAL.labels(result="invalid_signature").inc()
        logger.error("Missing X-Signature header")
        raise HTTPException(status_code=401, detail="invalid signature")
    
    body = await request.body()
    computed_sig = hmac.new(
        key=settings.WEBHOOK_SECRET.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_sig, x_signature):
        WEBHOOK_REQUESTS_TOTAL.labels(result="invalid_signature").inc()
        logger.error("Invalid X-Signature")
        raise HTTPException(status_code=401, detail="invalid signature")

# --- Routes ---

@app.on_event("startup")
async def startup_event():
    # Ensure DB tables exist
    await init_db()
    if not settings.WEBHOOK_SECRET:
        logger.critical("WEBHOOK_SECRET is missing!")

@app.post("/webhook")
@limiter.limit("60/minute") # Stricter limit for webhooks
async def webhook(
    payload: WebhookPayload,
    request: Request,

    db: AsyncSession = Depends(get_db),
    _verification: None = Depends(verify_signature)
):
    # If we are here, signature is valid.
    # Note: Pydantic validation happens before this body executes.
    # If pydantic fails, 422 is returned automatically.
    # We need to catch that for metrics/custom logging if strict requirement,
    # but FastAPI default is standard. 
    # The assignment says: "Invalid payload -> 422... no DB insert"
    
    inserted = await insert_message(db, payload)
    
    # Store context for the middleware to log in the "One JSON line"
    request.state.log_extra = {
        "message_id": payload.message_id,
        "dup": False,
        "result": "created"
    }
    
    if inserted:
        WEBHOOK_REQUESTS_TOTAL.labels(result="created").inc()
    else:
        request.state.log_extra["dup"] = True
        request.state.log_extra["result"] = "duplicate"
        WEBHOOK_REQUESTS_TOTAL.labels(result="duplicate").inc()
        
    return {"status": "ok"}

@app.get("/messages")
async def get_messages(
    limit: int = 50,
    offset: int = 0,
    from_: Optional[str] = Query(None, alias="from"),
    since: Optional[datetime] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Validation limits
    limit = max(1, min(100, limit))
    offset = max(0, offset)

    # Base query
    query = select(Message)
    count_query = select(func.count()).select_from(Message)
    
    # Filters
    filters = []
    if from_:
        filters.append(Message.from_msisdn == from_)
    if since:
        filters.append(Message.ts >= since)
    if q:
        filters.append(Message.text.ilike(f"%{q}%"))
    
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
        
    # Order
    query = query.order_by(Message.ts.asc(), Message.message_id.asc())
    
    # Pagination
    query = query.limit(limit).offset(offset)
    
    # Execute
    total = await db.scalar(count_query)
    result = await db.execute(query)
    messages = result.scalars().all()
    
    return {
        "data": [MessageResponse.model_validate(m) for m in messages],
        "total": total,
        "limit": limit,
        "offset": offset
    }



@app.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    # Total messages
    total_messages = await db.scalar(select(func.count()).select_from(Message))
    
    if total_messages == 0:
        return {
            "total_messages": 0,
            "senders_count": 0,
            "messages_per_sender": [],
            "first_message_ts": None,
            "last_message_ts": None
        }

    # Senders count (approximate or distinct count)
    senders_count = await db.scalar(select(func.count(func.distinct(Message.from_msisdn))))
    
    # Min/Max TS
    min_ts = await db.scalar(select(func.min(Message.ts)))
    max_ts = await db.scalar(select(func.max(Message.ts)))
    
    # Messages per sender (Top 10)
    top_senders_query = (
        select(Message.from_msisdn, func.count(Message.message_id).label("count"))
        .group_by(Message.from_msisdn)
        .order_by(desc("count"))
        .limit(10)
    )
    top_senders_res = await db.execute(top_senders_query)
    messages_per_sender = [
        {"from": row[0], "count": row[1]} for row in top_senders_res.all()
    ]
    
    return {
        "total_messages": total_messages,
        "senders_count": senders_count,
        "messages_per_sender": messages_per_sender,
        "first_message_ts": min_ts, # Pydantic/FastAPI handles datetime serialization
        "last_message_ts": max_ts
    }

@app.get("/health/live")
async def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    # Check DB
    try:
        await db.execute(text("SELECT 1"))
    except Exception as err:
        raise HTTPException(status_code=503, detail="Database not ready") from err
        
    # Check Secret
    if not settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Configuration invalid")
        
    return {"status": "ready"}

# @app.get("/metrics")
# async def metrics():
#     return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

