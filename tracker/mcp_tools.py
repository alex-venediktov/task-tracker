"""MCP-инструменты трекера поверх того же хранилища, что и REST."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from tracker.api import task_url
from tracker.config import Settings
from tracker.model import STATUSES, Task, TaskError
from tracker.store import NotFound, Store

PROJECT_HEADER = "x-project"

INSTRUCTIONS = (
    "Трекер задач по проектам: задача - md-файл с полями (проект, статус, теги) и постановкой "
    "markdown, id - сквозной номер. Свой проект подключение называет заголовком X-Project; задачу "
    "можно поставить в соседний проект, указав project, и перенести между проектами update_task. "
    "Статусы: " + ", ".join(STATUSES) + ". "
    "Постановку целиком отдаёт get_task с markdown=true - этот текст годится для /volna:task. "
    "Удаления нет: ненужную задачу переводят в done с комментарием."
)


def client_project(ctx: Context | None) -> str | None:
    headers = getattr(ctx, "headers", None) if ctx else None
    if not headers:
        return None
    value = (headers.get(PROJECT_HEADER) or headers.get("X-Project") or "").strip()
    return value or None


@contextlib.contextmanager
def explained() -> Iterator[None]:
    # Ошибки хранилища -> ToolError с текстом для модели (mcp/server/mcpserver/tools/base.py).
    try:
        yield
    except (TaskError, NotFound) as error:
        raise ToolError(str(error)) from error


def build_mcp(store: Store, settings: Settings) -> MCPServer:
    mcp = MCPServer("task-tracker", instructions=INSTRUCTIONS)

    def author(ctx: Context | None) -> str:
        return client_project(ctx) or "agent"

    def short(task: Task) -> dict:
        return {**task.summary(), "url": task_url(settings, task.id)}

    @mcp.tool()
    def list_projects() -> list[dict]:
        """Проекты трекера с числом задач по статусам. Проект появляется с первой задачей."""
        return store.projects()

    @mcp.tool()
    def list_tasks(
        project: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        ctx: Context | None = None,
    ) -> list[dict]:
        """Задачи кратко, без постановки, с фильтром по статусу и тегу. Без project - свой проект подключения, а если он не назван, все проекты."""
        with explained():
            found = store.tasks(project or client_project(ctx), status or None, tag or None)
            return [short(t) for t in found]

    @mcp.tool()
    def get_task(task_id: str, markdown: bool = False) -> dict | str:
        """Задача целиком по id (номер или заданный id). markdown=true - исходный md-файл текстом."""
        with explained():
            if markdown:
                return store.raw(task_id)
            return {**store.get(task_id).to_dict(), "url": task_url(settings, task_id)}

    @mcp.tool()
    def create_task(
        title: str,
        body: str = "",
        project: str | None = None,
        status: str = "backlog",
        tags: list[str] | None = None,
        task_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Поставить задачу. body - постановка markdown, лучше секциями «## Цель», «## Что сделать», «## Готово, когда». Без project - в свой проект подключения. Без task_id - следующий свободный номер."""
        target = project or client_project(ctx)
        if not target:
            raise ToolError("проект не указан: передай project или назови свой заголовком X-Project")
        with explained():
            task = store.create(
                target, title, body, status=status, tags=tags, author=author(ctx), task_id=task_id
            )
            return short(task)

    @mcp.tool()
    def update_task(
        task_id: str,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        new_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Поправить заголовок, постановку, теги, проект (перенос задачи, id сохраняется) или id (new_id: латинские буквы, цифры, - и _; прежняя ссылка перестаёт работать). Переданное поле заменяется целиком."""
        with explained():
            task = store.update(
                task_id,
                title=title,
                body=body,
                tags=tags,
                project=project,
                new_id=new_id,
                author=author(ctx),
            )
            return short(task)

    @mcp.tool()
    def move_task(task_id: str, status: str, ctx: Context | None = None) -> dict:
        """Перевести задачу в другой статус (колонку доски)."""
        with explained():
            return short(store.move(task_id, status, author=author(ctx)))

    @mcp.tool()
    def comment_task(task_id: str, text: str, ctx: Context | None = None) -> dict:
        """Дописать комментарий в секцию «Обсуждение» постановки."""
        with explained():
            return short(store.comment(task_id, text, author=author(ctx)))

    return mcp
