"""Хранилище задач: файл <id>.md на задачу в одном каталоге, чтение с диска на каждый запрос."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

from tracker import history
from tracker.model import (
    ID_RE,
    NUMBER_RE,
    STATUSES,
    Task,
    TaskError,
    add_comment,
    check_id,
    check_project,
    check_status,
    check_title,
    declared_id,
    id_key,
    parse,
    render,
)


class NotFound(LookupError):
    """Задачи с таким id нет."""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


class Store:
    def __init__(self, root: Path, *, git: bool = True) -> None:
        self.root = Path(root)
        self.git = git
        self._lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)

    def _task_files(self) -> list[Path]:
        files = [p for p in self.root.glob("*.md") if ID_RE.match(p.stem) and self._is_task(p)]
        return sorted(files, key=lambda p: id_key(p.stem))

    @staticmethod
    def _is_task(path: Path) -> bool:
        # Файл с номером в имени - задача всегда, с другим именем - только с тем же id во frontmatter.
        if NUMBER_RE.match(path.stem):
            return True
        return declared_id(path.read_text(encoding="utf-8-sig")) == path.stem

    def _taken(self, task_id: str) -> bool:
        # Занятым считается любой файл с этим именем, и не задача тоже: запись его затёрла бы.
        wanted = f"{task_id}.md".lower()
        return any(p.name.lower() == wanted for p in self.root.iterdir())

    def path_of(self, task_id: str) -> Path:
        return self.root / f"{check_id(task_id)}.md"

    def _read(self, path: Path) -> Task:
        return parse(path.read_text(encoding="utf-8-sig"), task_id=path.stem)

    def _all(self) -> list[Task]:
        return [self._read(path) for path in self._task_files()]

    def projects(self) -> list[dict]:
        counts: dict[str, dict[str, int]] = {}
        for task in self._all():
            if task.project:
                counts.setdefault(task.project, dict.fromkeys(STATUSES, 0))[task.status] += 1
        return [
            {"project": name, "tasks": sum(by.values()), "by_status": by}
            for name, by in sorted(counts.items())
        ]

    def tags(self, project: str | None = None) -> list[dict]:
        counts: dict[str, int] = {}
        for task in self._all():
            if project is None or task.project == project:
                for tag in task.tags:
                    counts[tag] = counts.get(tag, 0) + 1
        return [{"tag": tag, "tasks": n} for tag, n in sorted(counts.items())]

    def tasks(
        self, project: str | None = None, status: str | None = None, tag: str | None = None
    ) -> list[Task]:
        if status is not None:
            check_status(status)
        if project is not None:
            check_project(project)
        return [
            t
            for t in self._all()
            if (project is None or t.project == project)
            and (status is None or t.status == status)
            and (tag is None or tag in t.tags)
        ]

    def _existing(self, task_id: str) -> Path:
        path = self.path_of(task_id)
        if not path.is_file() or not self._is_task(path):
            raise NotFound(f"задачи #{task_id} нет")
        return path

    def get(self, task_id: str) -> Task:
        return self._read(self._existing(task_id))

    def raw(self, task_id: str) -> str:
        return self._existing(task_id).read_text(encoding="utf-8-sig")

    def create(
        self,
        project: str,
        title: str,
        body: str = "",
        *,
        status: str = "backlog",
        tags: list[str] | None = None,
        author: str = "human",
        task_id: str | None = None,
    ) -> Task:
        check_project(project)
        check_status(status)
        title = check_title(title)
        if task_id:
            task_id = check_id(task_id)
        with self._lock:
            files = self._task_files()
            if task_id and self._taken(task_id):
                raise TaskError(f"id {task_id} уже занят")
            numbers = [int(p.stem) for p in files if NUMBER_RE.match(p.stem)]
            stamp = now()
            task = Task(
                id=task_id or str(max(numbers, default=0) + 1),
                project=project,
                title=title,
                status=status,
                author=author,
                created=stamp,
                updated=stamp,
                tags=list(tags or []),
                body=body or "",
            )
            self._write(task, f"{author}: создана #{task.id} в {project} - {title}")
        return task

    def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        body: str | None = None,
        tags: list[str] | None = None,
        project: str | None = None,
        new_id: str | None = None,
        author: str = "human",
    ) -> Task:
        if project is not None:
            check_project(project)
        if new_id is not None:
            new_id = check_id(new_id)
        with self._lock:
            task = self.get(task_id)
            old_path = self.path_of(task.id)
            message = f"{author}: правка #{task.id}"
            if new_id is not None and new_id != task.id:
                if new_id.lower() == task.id.lower():
                    raise TaskError(f"id {new_id} отличается от {task.id} только регистром")
                if self._taken(new_id):
                    raise TaskError(f"id {new_id} уже занят")
                message += f", id {task.id} -> {new_id}"
                task.id = new_id
            if project is not None and project != task.project:
                message += f", проект {task.project or '-'} -> {project}"
                task.project = project
            if title is not None:
                task.title = check_title(title)
            if body is not None:
                task.body = body
            if tags is not None:
                task.tags = list(tags)
            task.updated = now()
            self._write(task, message, replaces=old_path)
        return task

    def move(self, task_id: str, status: str, *, author: str = "human") -> Task:
        check_status(status)
        with self._lock:
            task = self.get(task_id)
            previous = task.status
            task.status = status
            task.updated = now()
            self._write(task, f"{author}: #{task.id} {previous} -> {status}")
        return task

    def comment(self, task_id: str, text: str, *, author: str = "human") -> Task:
        with self._lock:
            task = self.get(task_id)
            stamp = now()
            task.body = add_comment(task.body, author=author, when=stamp.replace("T", " "), text=text)
            task.updated = stamp
            self._write(task, f"{author}: комментарий к #{task.id}")
        return task

    def _write(self, task: Task, message: str, *, replaces: Path | None = None) -> None:
        path = self.path_of(task.id)
        temp = path.with_name(f".{path.name}.tmp")
        # Атомарная запись: временный файл и замена.
        temp.write_text(render(task), encoding="utf-8", newline="\n")
        os.replace(temp, path)
        # Смена id: файл под прежним именем удаляется после записи нового.
        if replaces is not None and replaces != path:
            replaces.unlink(missing_ok=True)
        if self.git:
            history.commit(self.root, message)


__all__ = ["NotFound", "Store", "TaskError", "now"]
