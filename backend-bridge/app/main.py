from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.tasks import router as task_router
from app.services.event_bus import EventBus
from app.services.mock_engine import MockEngine
from app.services.task_service import TaskService


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bus = EventBus()
    task_service = TaskService(event_bus)
    engine = MockEngine(task_service, event_bus)
    task_service.set_engine(engine)

    app.state.event_bus = event_bus
    app.state.task_service = task_service
    yield


app = FastAPI(title="AI IDE Bridge API", version="v1alpha1", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True}


app.include_router(task_router)