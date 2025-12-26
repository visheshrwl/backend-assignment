import time
import hmac
import hashlib
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException, Depends, Header, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text
from app.config import get_settings
from app.storage import get_db, init_db, insert_message
from app.models import Message, WebhookPayload, MessageResponse
from app.logging_utils import logger
from app.metrics import HTTP_REQUESTS_TOTAL, WEBHOOK_REQUESTS_TOTAL, REQUEST_LATENCY_MS, generate_latest, CONTENT_TYPE_LATEST
import uuid

settings = get_settings()

app = FastAPI()

# --- Middleware ---

@app.middleware("http")
async def log_and_metrics_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Context for logging
    log_context = {
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
        HTTP_REQUESTS_TOTAL.labels(path=request.url.path, status=str(status_code)).inc()
        REQUEST_LATENCY_MS.observe(latency)
        
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
        raise HTTPException(status_code=401, detail={"detail": "invalid signature"})
    
    body = await request.body()
    computed_sig = hmac.new(
        key=settings.WEBHOOK_SECRET.encode(),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_sig, x_signature):
        WEBHOOK_REQUESTS_TOTAL.labels(result="invalid_signature").inc()
        logger.error("Invalid X-Signature")
        raise HTTPException(status_code=401, detail={"detail": "invalid signature"})

# --- Routes ---

@app.on_event("startup")
async def startup_event():
    # Ensure DB tables exist
    await init_db()
    if not settings.WEBHOOK_SECRET:
        logger.critical("WEBHOOK_SECRET is missing!")

@app.post("/webhook")
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
    
    if inserted:
        WEBHOOK_REQUESTS_TOTAL.labels(result="created").inc()
        logger.info("Message created", extra={"message_id": payload.message_id, "dup": False, "result": "created"})
    else:
        WEBHOOK_REQUESTS_TOTAL.labels(result="duplicate").inc()
        logger.info("Duplicate message", extra={"message_id": payload.message_id, "dup": True, "result": "duplicate"})
        
    return {"status": "ok"}

@app.get("/messages")
async def get_messages(
    limit: int = 50,
    offset: int = 0,
    from_: Optional[str] = fastapi.Query(None, alias="from"),
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

import fastapi # imported late for alias usage above

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
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")
        
    # Check Secret
    if not settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Configuration invalid")
        
    return {"status": "ready"}

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
