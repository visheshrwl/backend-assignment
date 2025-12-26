import hashlib
import hmac
import json

import pytest

WEBHOOK_SECRET = "testsecret"

def compute_signature(secret, body_bytes):
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

@pytest.mark.asyncio
async def test_webhook_invalid_signature(client):
    payload = {
        "message_id": "m1",
        "from": "+12345",
        "to": "+67890",
        "ts": "2025-01-01T00:00:00Z",
        "text": "Hello"
    }
    response = await client.post(
        "/webhook", 
        json=payload,
        headers={"X-Signature": "invalid"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid signature"}

@pytest.mark.asyncio
async def test_webhook_valid_signature_success(client):
    payload = {
        "message_id": "m1",
        "from": "+12345",
        "to": "+67890",
        "ts": "2025-01-01T00:00:00Z",
        "text": "Hello"
    }
    body_bytes = json.dumps(payload).encode() # Note: separators might matter for exact match if verify uses raw
    # But here we are using client.post(json=...) which uses standard separators.
    # To be safe in test matching what client sends, we can use client.post(content=...) or 
    # understand that httpx default is separators=(', ', ': ') ? No, default is (',', ':').
    # Let's rely on manual sig computation matching what httpx sends.
    # Actually, verify_sig reads request.body().
    
    # Let's pre-compute sig and send raw bytes to be sure.
    sig = compute_signature(WEBHOOK_SECRET, body_bytes)
    
    response = await client.post(
        "/webhook",
        content=body_bytes, # send raw bytes
        headers={"Content-Type": "application/json", "X-Signature": sig}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_webhook_duplicate(client):
    payload = {
        "message_id": "m_dup",
        "from": "+12345",
        "to": "+67890",
        "ts": "2025-01-01T00:00:00Z",
        "text": "Hello"
    }
    body_bytes = json.dumps(payload).encode()
    sig = compute_signature(WEBHOOK_SECRET, body_bytes)
    
    # First call
    response1 = await client.post(
        "/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig}
    )
    assert response1.status_code == 200
    
    # Second call
    response2 = await client.post(
        "/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Signature": sig}
    )
    assert response2.status_code == 200 # Idempotent success
