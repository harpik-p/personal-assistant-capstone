from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .approval_service import resolve_approval
from .storage import SQLiteStore


def _store() -> SQLiteStore:
    return SQLiteStore(os.getenv("ASSISTANT_DB_PATH", "assistant.db"))


async def dashboard(_: Request) -> JSONResponse:
    store = _store()
    tasks = [
        {
            "id": task.id, "title": task.title,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "status": task.status, "source_url": task.source_url,
        }
        for task in store.list_open()
    ]
    completed_tasks = [
        {
            "id": task.id, "title": task.title,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "status": task.status, "source_url": task.source_url,
        }
        for task in store.list_completed(10)
    ]
    processed = store.connection.execute("SELECT COUNT(*) FROM processed_items").fetchone()[0]
    return JSONResponse({
        "tasks": tasks,
        "completed_tasks": completed_tasks,
        "approvals": store.pending_approvals(),
        "audit": store.recent_audit(12),
        "processed": processed,
        "feedback_count": store.feedback_count(),
        "activities": store.latest_activity_recommendations(),
        "news": store.latest_news(),
    })


async def resolve(request: Request) -> JSONResponse:
    store = _store()
    try:
        body = await request.json()
        result = resolve_approval(
            store, request.path_params["approval_id"], str(body.get("decision", "")),
            body.get("edited_title"), body.get("edited_due_date"), body.get("feedback"),
        )
        return JSONResponse(result)
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def content_feedback(request: Request) -> JSONResponse:
    store = _store()
    try:
        body = await request.json()
        store.save_content_feedback(
            request.path_params["content_type"], str(body.get("item_key", "")),
            str(body.get("title", "")), str(body.get("context", "")),
            str(body.get("decision", "")),
        )
        store.record("content_feedback", {
            "content_type": request.path_params["content_type"],
            "title": body.get("title"), "decision": body.get("decision"),
        })
        return JSONResponse({"saved": True})
    except (ValueError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def complete_task(request: Request) -> JSONResponse:
    store = _store()
    try:
        task = store.complete_task(request.path_params["task_id"])
        store.record("task_completed", {"task_id": task.id, "title": task.title})
        return JSONResponse({"completed": True, "task_id": task.id})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def reopen_task(request: Request) -> JSONResponse:
    store = _store()
    try:
        task = store.reopen_task(request.path_params["task_id"])
        store.record("task_reopened", {"task_id": task.id, "title": task.title})
        return JSONResponse({"reopened": True, "task_id": task.id})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


app = Starlette(routes=[
    Route("/api/dashboard", dashboard, methods=["GET"]),
    Route("/api/approvals/{approval_id}", resolve, methods=["POST"]),
    Route("/api/feedback/{content_type}", content_feedback, methods=["POST"]),
    Route("/api/tasks/{task_id}/complete", complete_task, methods=["POST"]),
    Route("/api/tasks/{task_id}/reopen", reopen_task, methods=["POST"]),
])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
