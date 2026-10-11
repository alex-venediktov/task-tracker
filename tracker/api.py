"""REST: проекты и задачи в JSON, задача сырым markdown для постановки."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from tracker.config import Settings
from tracker.model import STATUS_LABELS, STATUSES, Task
from tracker.store import Store


class TaskIn(BaseModel):
    project: str
    title: str
    id: str | None = None
    body: str = ""
    status: str = "backlog"
    tags: list[str] = Field(default_factory=list)
    author: str = "human"


class TaskPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    tags: list[str] | None = None
    project: str | None = None
    id: str | None = None
    author: str = "human"


class MoveIn(BaseModel):
    status: str
    author: str = "human"


class CommentIn(BaseModel):
    text: str
    author: str = "human"


def task_url(settings: Settings, task_id: str) -> str:
    return f"{settings.public_url}/t/{task_id}.md"


def build_router(store: Store, settings: Settings) -> APIRouter:
    router = APIRouter()

    def full(task: Task) -> dict:
        return {**task.to_dict(), "url": task_url(settings, task.id)}

    def short(task: Task) -> dict:
        return {**task.summary(), "url": task_url(settings, task.id)}

    @router.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @router.get("/api/statuses")
    def statuses() -> list[dict]:
        return [{"status": s, "label": STATUS_LABELS[s]} for s in STATUSES]

    @router.get("/api/projects")
    def projects() -> list[dict]:
        return store.projects()

    @router.get("/api/tags")
    def tags(project: str | None = None) -> list[dict]:
        return store.tags(project or None)

    @router.get("/api/tasks")
    def tasks(
        project: str | None = None, status: str | None = None, tag: str | None = None
    ) -> list[dict]:
        return [short(t) for t in store.tasks(project or None, status or None, tag or None)]

    @router.post("/api/tasks", status_code=201)
    def create(data: TaskIn) -> dict:
        task = store.create(
            data.project,
            data.title,
            data.body,
            status=data.status,
            tags=data.tags,
            author=data.author,
            task_id=data.id or None,
        )
        return full(task)

    @router.get("/api/tasks/{task_id}")
    def get(task_id: str) -> dict:
        return full(store.get(task_id))

    @router.patch("/api/tasks/{task_id}")
    def update(task_id: str, data: TaskPatch) -> dict:
        task = store.update(
            task_id,
            title=data.title,
            body=data.body,
            tags=data.tags,
            project=data.project,
            new_id=data.id,
            author=data.author,
        )
        return full(task)

    @router.post("/api/tasks/{task_id}/move")
    def move(task_id: str, data: MoveIn) -> dict:
        return full(store.move(task_id, data.status, author=data.author))

    @router.post("/api/tasks/{task_id}/comments")
    def comment(task_id: str, data: CommentIn) -> dict:
        return full(store.comment(task_id, data.text, author=data.author))

    @router.get("/t/{task_id}.md", response_class=PlainTextResponse)
    def raw(task_id: str) -> PlainTextResponse:
        return PlainTextResponse(store.raw(task_id), media_type="text/markdown; charset=utf-8")

    return router
