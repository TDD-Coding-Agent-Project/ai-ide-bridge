from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from app.models.common import (
    NetworkPolicy,
    TaskMode,
    TaskStatus,
    WorkspaceMode,
    utc_now,
)


class RepoRef(BaseModel):
    rootPath: str
    branch: str | None = None


class Selection(BaseModel):
    startLine: int
    startCol: int
    endLine: int
    endCol: int


class ContextPayload(BaseModel):
    activeFile: str | None = None
    selection: Selection | None = None
    openFiles: list[str] = Field(default_factory=list)
    diagnostics: list[dict] = Field(default_factory=list)
    gitDiff: str = ""
    terminalTail: str = ""
    testLogs: str = ""


class Policy(BaseModel):
    workspaceMode: WorkspaceMode = "local"
    network: NetworkPolicy = "deny"
    requireApprovalFor: list[str] = Field(default_factory=list)
    maxDurationSec: int = 600
    maxOutputBytes: int = 262144
    writablePaths: list[str] = Field(default_factory=list)
    envAllowlist: list[str] = Field(default_factory=list)


class CreateTaskRequest(BaseModel):
    requestId: str | None = None
    sessionId: str | None = None
    protocolVersion: str = "v1alpha1"
    mode: TaskMode
    userPrompt: str
    repo: RepoRef
    context: ContextPayload = Field(default_factory=ContextPayload)
    policy: Policy


class CommandApprovalRequest(BaseModel):
    approved: bool
    reason: str | None = None


class TaskRecord(BaseModel):
    taskId: str
    mode: TaskMode
    status: TaskStatus
    workspaceMode: WorkspaceMode
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)
    latestMessage: str | None = None