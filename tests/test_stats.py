import pytest
from datetime import datetime
from app.models import Message

@pytest.mark.asyncio
async def test_stats_empty(client, db_session):
    resp = await client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_messages"] == 0

@pytest.mark.asyncio
async def test_stats_populated(client, db_session):
    msgs = [
        Message(message_id="m1", from_msisdn="+100", to_msisdn="+999", ts=datetime(2025,1,1), text="A"),
        Message(message_id="m2", from_msisdn="+100", to_msisdn="+999", ts=datetime(2025,1,2), text="B"),
        Message(message_id="m3", from_msisdn="+200", to_msisdn="+999", ts=datetime(2025,1,3), text="C"),
    ]
    db_session.add_all(msgs)
    await db_session.commit()
    
    resp = await client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["total_messages"] == 3
    assert data["senders_count"] == 2
    # +100 has 2, +200 has 1. Sorted count desc.
    assert data["messages_per_sender"][0]["from"] == "+100"
    assert data["messages_per_sender"][0]["count"] == 2
    
    assert data["first_message_ts"].startswith("2025-01-01")
    assert data["last_message_ts"].startswith("2025-01-03")
