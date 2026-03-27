from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.models.common import gen_id, utc_now
from app.models.task import CreateTaskRequest, TaskRecord
from app.services.event_bus import EventBus


class TaskNotFoundError(Exception):
    pass


class CommandApprovalNotFoundError(Exception):
    pass


@dataclass
class CommandRequestRecord:
    task_id: str
    command_id: str
    command: str
    cwd: str
    risk_level: str
    reason: str
    status: str  # pending / approved / rejected / expired


class TaskService:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.tasks: dict[str, TaskRecord] = {}
        self.task_requests: dict[str, CreateTaskRequest] = {}
        self.background_tasks: dict[str, asyncio.Task] = {}

        # 真正用于 await 的 future
        self.pending_approvals: dict[str, asyncio.Future[bool]] = {}

        # 新增：正式保存命令请求状态
        self.command_requests: dict[str, CommandRequestRecord] = {}

        self.engine = None

    def set_engine(self, engine) -> None:
        self.engine = engine

    def get_task(self, task_id: str) -> TaskRecord:
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        return task

    def get_request(self, task_id: str) -> CreateTaskRequest:
        req = self.task_requests.get(task_id)
        if req is None:
            raise TaskNotFoundError(f"Task request {task_id} not found")
        return req

    def get_command_request(self, task_id: str, command_id: str) -> CommandRequestRecord:
        record = self.command_requests.get(command_id)
        if record is None or record.task_id != task_id:
            raise CommandApprovalNotFoundError(
                f"Command approval {command_id} not found for task {task_id}"
            )
        return record

    async def create_task(self, req: CreateTaskRequest) -> TaskRecord:
        if self.engine is None:
            raise RuntimeError("Engine is not configured")

        task = TaskRecord(
            taskId=gen_id("task"),
            mode=req.mode,
            status="queued",
            workspaceMode=req.policy.workspaceMode,
            latestMessage="Task queued",
        )
        self.tasks[task.taskId] = task
        self.task_requests[task.taskId] = req

        await self.event_bus.publish(
            task.taskId,
            "task.status",
            {"status": "queued", "message": "Task queued"},
        )

        runner = asyncio.create_task(self.engine.run_task(task.taskId))
        self.background_tasks[task.taskId] = runner
        return task

    async def set_status(self, task_id: str, status: str, message: str | None = None) -> TaskRecord:
        task = self.get_task(task_id)
        task.status = status
        task.updatedAt = utc_now()
        task.latestMessage = message
        await self.event_bus.publish(
            task_id,
            "task.status",
            {"status": status, "message": message or ""},
        )
        return task

    async def cancel_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)
        runner = self.background_tasks.get(task_id)

        if runner and not runner.done():
            runner.cancel()
            return task

        if task.status not in {"completed", "failed", "cancelled"}:
            await self.set_status(task_id, "cancelled", "Task cancelled")
            await self.event_bus.publish(
                task_id,
                "task.final",
                {"outcome": "cancelled", "summary": "Task cancelled by user"},
            )
        return task

    async def request_command_approval(
        self,
        task_id: str,
        command_id: str,
        command: str,
        cwd: str,
        risk_level: str,
        reason: str,
    ) -> None:
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self.pending_approvals[command_id] = future

        self.command_requests[command_id] = CommandRequestRecord(
            task_id=task_id,
            command_id=command_id,
            command=command,
            cwd=cwd,
            risk_level=risk_level,
            reason=reason,
            status="pending",
        )

        await self.set_status(task_id, "awaiting_approval", "Waiting for command approval")
        await self.event_bus.publish(
            task_id,
            "task.command.request",
            {
                "commandId": command_id,
                "command": command,
                "cwd": cwd,
                "riskLevel": risk_level,
                "reason": reason,
            },
        )

    async def wait_for_approval(self, task_id: str, command_id: str, timeout: int = 300) -> bool:
        future = self.pending_approvals.get(command_id)
        record = self.command_requests.get(command_id)

        if future is None or record is None or record.task_id != task_id:
            raise CommandApprovalNotFoundError(
                f"Command approval {command_id} not found for task {task_id}"
            )

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            record.status = "expired"
            raise
        finally:
            self.pending_approvals.pop(command_id, None)

    def approve_command(self, task_id: str, command_id: str, approved: bool) -> None:
        record = self.get_command_request(task_id, command_id)

        if record.status != "pending":
            raise CommandApprovalNotFoundError(
                f"Command {command_id} is already resolved with status={record.status}"
            )

        future = self.pending_approvals.get(command_id)
        if future is None:
            raise CommandApprovalNotFoundError(
                f"Command {command_id} has no active approval future"
            )

        record.status = "approved" if approved else "rejected"

        if not future.done():
            future.set_result(approved)