from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func
from app.config import get_settings
from app.models import Base, Message, WebhookPayload
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)

settings = get_settings()

# Adapt URL for async sqlite
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite://"):
    db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)

engine = create_async_engine(
    db_url,
    echo=False,
    connect_args={"check_same_thread": False} # Needed for SQLite
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def insert_message(session: AsyncSession, payload: WebhookPayload) -> bool:
    """
    Inserts a message. Returns True if inserted, False if duplicate.
    """
    msg = Message(
        message_id=payload.message_id,
        from_msisdn=payload.from_msisdn,
        to_msisdn=payload.to_msisdn,
        ts=payload.ts,
        text=payload.text
    )
    session.add(msg)
    try:
        await session.commit()
        return True
    except IntegrityError:
        await session.rollback()
        return False
