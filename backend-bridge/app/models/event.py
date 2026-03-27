from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.common import EventType, gen_id, utc_now


class EventEnvelope(BaseModel):
    eventId: str = Field(default_factory=lambda: gen_id("evt"))
    taskId: str
    seq: int
    type: EventType
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)