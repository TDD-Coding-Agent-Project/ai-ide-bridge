from __future__ import annotations

import asyncio

from app.models.common import gen_id
from app.services.event_bus import EventBus
from app.services.task_service import TaskService


class MockEngine:
    def __init__(self, task_service: TaskService, event_bus: EventBus) -> None:
        self.task_service = task_service
        self.event_bus = event_bus

    async def run_task(self, task_id: str) -> None:
        try:
            req = self.task_service.get_request(task_id)

            await self.task_service.set_status(task_id, "planning", "Building execution plan")
            await self.event_bus.publish(
                task_id,
                "task.plan",
                {
                    "steps": [
                        "Read current task context",
                        "Inspect related files",
                        "Run one command after approval",
                        "Prepare patch output",
                    ]
                },
            )
            await asyncio.sleep(0.5)

            await self.task_service.set_status(task_id, "running", "Inspecting project files")
            await self.event_bus.publish(
                task_id,
                "task.log",
                {
                    "stream": "stdout",
                    "text": f"Opening repo: {req.repo.rootPath}\nActive file: {req.context.activeFile or 'N/A'}\n",
                },
            )
            await asyncio.sleep(0.5)

            command_id = gen_id("cmd")
            await self.task_service.request_command_approval(
                task_id=task_id,
                command_id=command_id,
                command="pytest -q",
                cwd=req.repo.rootPath,
                risk_level="medium",
                reason="Run tests to inspect current failures",
            )

            approved = await self.task_service.wait_for_approval(task_id, command_id, timeout=300)

            if not approved:
                await self.event_bus.publish(
                    task_id,
                    "task.error",
                    {
                        "code": "TOOL_ERROR",
                        "message": "Command was rejected by the user",
                        "retryable": True,
                    },
                )
                await self.task_service.set_status(task_id, "failed", "Command rejected")
                await self.event_bus.publish(
                    task_id,
                    "task.final",
                    {
                        "outcome": "failed",
                        "summary": "Task stopped because the command was rejected",
                    },
                )
                return

            await self.task_service.set_status(task_id, "running", "Running approved command")
            await self.event_bus.publish(
                task_id,
                "task.command.result",
                {
                    "commandId": command_id,
                    "exitCode": 1,
                    "stdout": "1 failed, 3 passed\n",
                    "stderr": "",
                },
            )
            await asyncio.sleep(0.5)

            active_file = req.context.activeFile or "src/example.py"

            await self.task_service.set_status(task_id, "patch_ready", "Patch ready for review")
            await self.event_bus.publish(
                task_id,
                "task.patch",
                {
                    "patchId": gen_id("patch"),
                    "summary": "Fix boundary check in parser",
                    "files": [
                        {
                            "path": active_file,
                            "changeType": "modify",
                            "unifiedDiff": (
                                "--- a/{0}\n"
                                "+++ b/{0}\n"
                                "@@ -40,3 +40,5 @@\n"
                                "-if idx > len(items):\n"
                                "+if idx >= len(items):\n"
                                "     return None\n"
                                "+# guard against out-of-range access\n"
                            ).format(active_file),
                            "ops": [
                                {
                                    "op": "replace_range",
                                    "startLine": 40,
                                    "endLine": 41,
                                    "content": "if idx >= len(items):\n    return None\n",
                                }
                            ],
                        }
                    ],
                },
            )

            await self.event_bus.publish(
                task_id,
                "task.test.result",
                {"framework": "pytest", "passed": 4, "failed": 0, "skipped": 0},
            )

            await self.task_service.set_status(task_id, "completed", "Task completed")
            await self.event_bus.publish(
                task_id,
                "task.final",
                {
                    "outcome": "completed",
                    "summary": "Mock task completed successfully",
                },
            )

        except asyncio.CancelledError:
            await self.task_service.set_status(task_id, "cancelled", "Task cancelled")
            await self.event_bus.publish(
                task_id,
                "task.final",
                {"outcome": "cancelled", "summary": "Task cancelled by user"},
            )
            raise
        except Exception as exc:
            await self.task_service.set_status(task_id, "failed", "Unhandled backend error")
            await self.event_bus.publish(
                task_id,
                "task.error",
                {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "retryable": False,
                },
            )
            await self.event_bus.publish(
                task_id,
                "task.final",
                {"outcome": "failed", "summary": "Task failed with internal error"},
            )