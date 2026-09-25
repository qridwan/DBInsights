"""DBInsight collector service.

    uv run uvicorn api.app:app --port 8700

Receives batches of runtime events from @dbinsight/collector and stores them
in the results database ($DBINSIGHT_RESULTS_DATABASE_URL).
"""

import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request

from .events import OperationEvent
from .storage import EventStore, PostgresEventStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "store"):
        app.state.store = PostgresEventStore(os.environ["DBINSIGHT_RESULTS_DATABASE_URL"])
    yield


app = FastAPI(title="DBInsight collector", lifespan=lifespan)


def get_store(request: Request) -> EventStore:
    return request.app.state.store


StoreDep = Annotated[EventStore, Depends(get_store)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/operations", status_code=202)
def ingest(events: list[OperationEvent], store: StoreDep) -> dict[str, int]:
    return {"accepted": store.ingest(events)}


@app.get("/v1/operations")
def list_operations(
    store: StoreDep,
    app_name: Annotated[str | None, Query(alias="app")] = None,
    request_id: Annotated[str | None, Query(alias="requestId")] = None,
    route: str | None = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 100,
) -> list[dict[str, Any]]:
    return store.operations(app=app_name, request_id=request_id, route=route, limit=limit)
