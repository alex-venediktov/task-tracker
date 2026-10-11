"""Задача и её md-файл: frontmatter YAML и тело markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

STATUSES = ("backlog", "todo", "doing", "review", "done")
STATUS_LABELS = {
    "backlog": "Бэклог",
    "todo": "К работе",
    "doing": "В работе",
    "review": "Проверка",
    "done": "Готово",
}

PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
NUMBER_RE = re.compile(r"^[1-9][0-9]{0,8}$")
RESERVED_IDS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)

KNOWN_KEYS = ("id", "project", "title", "status", "author", "created", "updated", "tags")
DISCUSSION = "## Обсуждение"


class TaskError(ValueError):
    """Неверные данные задачи: имя проекта, статус, id, пустой заголовок."""


@dataclass
class Task:
    id: str
    project: str
    title: str
    status: str = "backlog"
    author: str = "human"
    created: str = ""
    updated: str = ""
    tags: list[str] = field(default_factory=list)
    body: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project": self.project,
            "title": self.title,
            "status": self.status,
            "author": self.author,
            "updated": self.updated,
            "tags": list(self.tags),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.summary(), "created": self.created, "body": self.body, "extra": self.extra}


def check_project(name: str) -> str:
    if not isinstance(name, str) or not PROJECT_RE.match(name):
        raise TaskError(
            f"имя проекта {name!r} не подходит: строчные латинские буквы, цифры и дефис, до 63 знаков"
        )
    return name


def check_status(status: str) -> str:
    if status not in STATUSES:
        raise TaskError(f"статус {status!r} неизвестен, допустимы: {', '.join(STATUSES)}")
    return status


def check_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise TaskError("заголовок задачи пуст")
    if "\n" in title:
        raise TaskError("заголовок задачи - одна строка")
    return title


def check_id(task_id: str) -> str:
    task_id = str(task_id or "").strip().lstrip("#")
    if not ID_RE.match(task_id) or task_id.lower() in RESERVED_IDS:
        raise TaskError(
            f"id {task_id!r} не подходит: латинские буквы, цифры, дефис и подчёркивание, до 64 знаков"
        )
    return task_id


def id_key(task_id: str) -> tuple[int, int, str]:
    """Порядок задач: сначала номера по возрастанию, затем остальные id по алфавиту."""
    if NUMBER_RE.match(task_id):
        return (0, int(task_id), "")
    return (1, 0, task_id.lower())


def _text(value: Any) -> str:
    # Дата или время из YAML -> строка ISO.
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def declared_id(text: str) -> str:
    """Id, записанный во frontmatter файла; нет frontmatter или ключа - пустая строка."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return ""
    loaded = yaml.safe_load(match.group(1))
    return _text(loaded.get("id")).strip() if isinstance(loaded, dict) else ""


def parse(text: str, *, task_id: str) -> Task:
    """Разбор файла задачи; id берётся из имени файла, проект - из frontmatter (нет - пустой)."""
    meta: dict[str, Any] = {}
    body = text
    match = FRONTMATTER_RE.match(text)
    if match:
        loaded = yaml.safe_load(match.group(1))
        if isinstance(loaded, dict):
            meta = loaded
        body = text[match.end():]

    status = _text(meta.get("status")) or "backlog"
    return Task(
        id=task_id,
        project=_text(meta.get("project")).strip(),
        title=_text(meta.get("title")) or f"#{task_id}",
        status=status if status in STATUSES else "backlog",
        author=_text(meta.get("author")) or "human",
        created=_text(meta.get("created")),
        updated=_text(meta.get("updated")),
        tags=_tags(meta.get("tags")),
        body=body.strip("\r\n"),
        extra={key: value for key, value in meta.items() if key not in KNOWN_KEYS},
    )


def render(task: Task) -> str:
    meta: dict[str, Any] = {
        "id": int(task.id) if NUMBER_RE.match(task.id) else task.id,
        "project": task.project,
        "title": task.title,
        "status": task.status,
        "author": task.author,
        "created": task.created,
        "updated": task.updated,
        "tags": list(task.tags),
    }
    meta.update(task.extra)
    head = yaml.safe_dump(
        meta, allow_unicode=True, sort_keys=False, default_flow_style=None, width=1000
    )
    body = task.body.strip("\r\n")
    return f"---\n{head}---\n\n{body}\n" if body.strip() else f"---\n{head}---\n"


def add_comment(body: str, *, author: str, when: str, text: str) -> str:
    """Комментарий подсекцией в конец секции «Обсуждение»; секции нет - она дописывается в конец."""
    text = (text or "").strip()
    if not text:
        raise TaskError("комментарий пуст")
    entry = [f"### {when} - {author}", "", text]

    lines = body.strip("\r\n").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == DISCUSSION), None)
    if start is None:
        head = [*lines, ""] if lines else []
        return "\n".join([*head, DISCUSSION, "", *entry])

    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    section = lines[start:end]
    while section and not section[-1].strip():
        section.pop()
    rest = lines[end:]
    tail = ["", *rest] if rest else []
    return "\n".join([*lines[:start], *section, "", *entry, *tail])
