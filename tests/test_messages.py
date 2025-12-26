import pytest
import asyncio
from datetime import datetime, timedelta
from app.models import Message
from sqlalchemy import text

# Helper to populate DB
async def seed_messages(session):
    msgs = [
        Message(message_id="m1", from_msisdn="+100", to_msisdn="+999", ts=datetime(2025,1,1,10,0,0), text="Msg 1"),
        Message(message_id="m2", from_msisdn="+100", to_msisdn="+999", ts=datetime(2025,1,1,11,0,0), text="Msg 2"),
        Message(message_id="m3", from_msisdn="+200", to_msisdn="+999", ts=datetime(2025,1,1,12,0,0), text="Other"),
        Message(message_id="m4", from_msisdn="+100", to_msisdn="+999", ts=datetime(2025,1,1,9,0,0), text="Early"),
    ]
    session.add_all(msgs)
    await session.commit()

@pytest.mark.asyncio
async def test_listing_pagination(client, db_session):
    await seed_messages(db_session)
    
    # Default list (ordered by ts ASC: m4, m1, m2, m3)
    resp = await client.get("/messages")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert len(data["data"]) == 4
    assert data["data"][0]["message_id"] == "m4" # Early

    # Limit/Offset
    resp = await client.get("/messages?limit=2&offset=1")
    data = resp.json()
    assert len(data["data"]) == 2
    assert data["data"][0]["message_id"] == "m1" 

@pytest.mark.asyncio
async def test_listing_filters(client, db_session):
    await seed_messages(db_session)
    
    # Filter by from
    resp = await client.get("/messages?from=%2B200") # +200
    data = resp.json()
    assert data["total"] == 1
    assert data["data"][0]["message_id"] == "m3"
    
    # Text search
    resp = await client.get("/messages?q=Msg")
    data = resp.json()
    assert data["total"] == 2 # m1, m2
