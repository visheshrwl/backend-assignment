from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime
from sqlalchemy.sql import func

# --- Pydantic Models for Validation ---

class WebhookPayload(BaseModel):
    message_id: str = Field(..., min_length=1)
    from_msisdn: str = Field(..., alias="from")
    to_msisdn: str = Field(..., alias="to")
    ts: datetime
    text: Optional[str] = Field(None, max_length=4096)

    @field_validator('from_msisdn', 'to_msisdn')
    def validate_e164(cls, v):
        # E.164 simple check: start with +, then digits only. 
        # (Assignment says: start with +, then digits only)
        if not re.match(r'^\+\d+$', v):
            raise ValueError('Must be E.164 format (start with +, digits only)')
        return v

    class Config:
        populate_by_name = True

class MessageResponse(BaseModel):
    message_id: str
    from_msisdn: str = Field(..., serialization_alias="from")
    to_msisdn: str = Field(..., serialization_alias="to")
    ts: datetime
    text: Optional[str] = None

    class Config:
        from_attributes = True

# --- SQLAlchemy Models ---

class Base(DeclarativeBase):
    pass

class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    from_msisdn: Mapped[str] = mapped_column(String, nullable=False)
    to_msisdn: Mapped[str] = mapped_column(String, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False) # Stores as ISO string in SQLite
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=func.now()
    )
