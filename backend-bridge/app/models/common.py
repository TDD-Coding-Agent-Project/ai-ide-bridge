from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


TaskMode = Literal[
    "repo_chat",
    "edit_selection",
    "fix_test",
    "refactor_scope",
    "explain_error",
]

TaskStatus = Literal[
    "queued",
    "planning",
    "awaiting_approval",
    "running",
    "patch_ready",
    "completed",
    "failed",
    "cancelled",
]

WorkspaceMode = Literal["local", "docker", "remote"]
NetworkPolicy = Literal["allow", "deny"]

EventType = Literal[
    "task.status",
    "task.plan",
    "task.log",
    "task.command.request",
    "task.command.result",
    "task.patch",
    "task.test.result",
    "task.error",
    "task.final",
]

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "AUTH_ERROR",
    "WORKSPACE_ERROR",
    "MODEL_ERROR",
    "TOOL_ERROR",
    "PATCH_ERROR",
    "TIMEOUT_ERROR",
    "INTERNAL_ERROR",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    success: bool = True
    requestId: str | None = None
    data: Any = None
    error: ErrorBody | None = None
    protocolVersion: str = "v1alpha1"