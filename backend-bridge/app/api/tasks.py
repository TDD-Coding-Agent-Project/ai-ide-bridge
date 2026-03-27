from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status

from app.models.common import ErrorBody, ResponseEnvelope
from app.models.task import CommandApprovalRequest, CreateTaskRequest
from app.services.task_service import (
    CommandApprovalNotFoundError,
    TaskNotFoundError,
)

router = APIRouter(prefix="/v1/tasks", tags=["Tasks"])


@router.post("", response_model=ResponseEnvelope)
async def create_task(payload: CreateTaskRequest, request: Request) -> ResponseEnvelope:
    task_service = request.app.state.task_service
    task = await task_service.create_task(payload)
    return ResponseEnvelope(
        success=True,
        requestId=payload.requestId,
        data={"task": task},
    )


@router.get("/{task_id}", response_model=ResponseEnvelope)
async def get_task(task_id: str, request: Request) -> ResponseEnvelope:
    task_service = request.app.state.task_service
    try:
        task = task_service.get_task(task_id)
    except TaskNotFoundError:
        return ResponseEnvelope(
            success=False,
            error=ErrorBody(
                code="VALIDATION_ERROR",
                message=f"Task {task_id} not found",
                retryable=False,
            ),
        )
    return ResponseEnvelope(success=True, data={"task": task})


@router.post("/{task_id}/cancel", response_model=ResponseEnvelope)
async def cancel_task(task_id: str, request: Request) -> ResponseEnvelope:
    task_service = request.app.state.task_service
    try:
        task = await task_service.cancel_task(task_id)
    except TaskNotFoundError:
        return ResponseEnvelope(
            success=False,
            error=ErrorBody(
                code="VALIDATION_ERROR",
                message=f"Task {task_id} not found",
                retryable=False,
            ),
        )
    return ResponseEnvelope(success=True, data={"task": task})


@router.post("/{task_id}/commands/{command_id}/approval", response_model=ResponseEnvelope)
async def approve_command(
    task_id: str,
    command_id: str,
    payload: CommandApprovalRequest,
    request: Request,
) -> ResponseEnvelope:
    task_service = request.app.state.task_service

    try:
        task_service.get_task(task_id)
        task_service.approve_command(task_id, command_id, payload.approved)
    except TaskNotFoundError:
        return ResponseEnvelope(
            success=False,
            error=ErrorBody(
                code="VALIDATION_ERROR",
                message=f"Task {task_id} not found",
                retryable=False,
            ),
        )
    except CommandApprovalNotFoundError:
        return ResponseEnvelope(
            success=False,
            error=ErrorBody(
                code="VALIDATION_ERROR",
                message=f"Command {command_id} not found or already resolved",
                retryable=False,
            ),
        )

    return ResponseEnvelope(
        success=True,
        data={
            "taskId": task_id,
            "commandId": command_id,
            "approved": payload.approved,
            "reason": payload.reason,
        },
    )


@router.websocket("/{task_id}/events")
async def task_events(websocket: WebSocket, task_id: str) -> None:
    task_service = websocket.app.state.task_service
    event_bus = websocket.app.state.event_bus

    try:
        task_service.get_task(task_id)
    except TaskNotFoundError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    queue = event_bus.subscribe(task_id)
    history = event_bus.get_history(task_id)
    last_seq = 0

    try:
        for event in history:
            await websocket.send_json(event.model_dump(mode="json"))
            last_seq = event.seq

        while True:
            event = await queue.get()
            if event.seq <= last_seq:
                continue
            await websocket.send_json(event.model_dump(mode="json"))
            last_seq = event.seq

    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(task_id, queue)