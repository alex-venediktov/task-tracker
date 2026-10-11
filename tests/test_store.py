"""Хранилище задач на диске: сквозной номер, проект полем, фильтры, ручные правки, история в git."""

import shutil
import subprocess

import pytest

from tracker import history
from tracker.model import TaskError
from tracker.store import NotFound, Store


def test_create_in_empty_store_assigns_number_one_and_writes_file(tmp_path):
    """Первая задача получает номер 1 и ложится файлом 1.md с проектом во frontmatter."""
    store = Store(tmp_path, git=False)

    task = store.create("alpha", "Первая", "## Цель\n\nпроверить")

    assert task.id == "1"
    text = (tmp_path / "1.md").read_text(encoding="utf-8")
    assert text.startswith("---\nid: 1\nproject: alpha\ntitle: Первая\nstatus: backlog\n")
    assert text.endswith("## Цель\n\nпроверить\n")


def test_create_numbers_are_shared_across_projects(tmp_path):
    """Номер сквозной: задача другого проекта берёт следующий номер, а не свою единицу."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Первая")

    assert store.create("beta", "Вторая").id == "2"


def test_create_takes_number_after_max_existing(tmp_path):
    """Номер новой задачи следует за наибольшим в каталоге, даже если есть пропуски."""
    (tmp_path / "7.md").write_text("---\nproject: alpha\ntitle: старая\n---\n", encoding="utf-8")
    store = Store(tmp_path, git=False)

    assert store.create("alpha", "Новая").id == "8"


def test_get_after_manual_edit_returns_new_content(tmp_path):
    """Правка файла руками видна при следующем чтении без перезапуска."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Было")
    path = tmp_path / "1.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Было", "Стало"), encoding="utf-8")

    assert store.get("1").title == "Стало"


def test_update_keeps_unknown_frontmatter_keys(tmp_path):
    """Правка через хранилище не теряет ключи frontmatter, которых оно не знает."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Задача")
    path = tmp_path / "1.md"
    path.write_text(path.read_text(encoding="utf-8").replace("tags: []", "tags: []\norder: 5"), encoding="utf-8")

    store.update("1", title="Другая")

    assert "order: 5" in path.read_text(encoding="utf-8")


def test_update_project_moves_task_and_keeps_id(tmp_path):
    """Смена проекта переносит задачу в другой проект: номер и файл те же, списки проектов меняются."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Задача")

    task = store.update("1", project="beta")

    assert (task.id, task.project) == ("1", "beta")
    assert "project: beta" in (tmp_path / "1.md").read_text(encoding="utf-8")
    assert store.tasks("alpha") == []
    assert [t.id for t in store.tasks("beta")] == ["1"]


def test_tasks_filter_by_project_status_and_tag(tmp_path):
    """Фильтры проекта, статуса и метки сочетаются; без фильтров - все задачи."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "A1", tags=["ui"])
    store.create("alpha", "A2", status="doing", tags=["ui", "api"])
    store.create("beta", "B1", tags=["ui"])

    assert [t.id for t in store.tasks()] == ["1", "2", "3"]
    assert [t.id for t in store.tasks("alpha", tag="ui")] == ["1", "2"]
    assert [t.id for t in store.tasks(tag="api")] == ["2"]
    assert [t.id for t in store.tasks("alpha", "doing", "ui")] == ["2"]


def test_projects_and_tags_are_collected_from_fields(tmp_path):
    """Проекты и метки - значения полей задач с числом задач; файл без проекта в проекты не входит."""
    store = Store(tmp_path, git=False)
    store.create("beta", "B1", tags=["ui"])
    store.create("alpha", "A1", status="done", tags=["ui", "api"])
    (tmp_path / "3.md").write_text("Задача без frontmatter\n", encoding="utf-8")

    assert [(p["project"], p["tasks"]) for p in store.projects()] == [("alpha", 1), ("beta", 1)]
    assert store.projects()[0]["by_status"]["done"] == 1
    assert store.tags() == [{"tag": "api", "tasks": 1}, {"tag": "ui", "tasks": 2}]
    assert store.tags("beta") == [{"tag": "ui", "tasks": 1}]
    assert [t.project for t in store.tasks()] == ["beta", "alpha", ""]


def test_create_with_given_id_keeps_numbering(tmp_path):
    """Заданный id становится именем файла, а следующий номер считается только по номерам."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Первая")

    named = store.create("alpha", "Своя", task_id="volna-url")

    assert named.id == "volna-url"
    assert "id: volna-url" in (tmp_path / "volna-url.md").read_text(encoding="utf-8")
    assert store.create("alpha", "Третья").id == "2"
    assert [t.id for t in store.tasks()] == ["1", "2", "volna-url"]


def test_update_id_renames_file_and_keeps_content(tmp_path):
    """Смена id переименовывает файл: прежнего нет, содержимое и проект на месте, id во frontmatter новый."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Задача", "## Цель\n\nтекст")

    task = store.update("1", new_id="TT-7")

    assert task.id == "TT-7"
    assert not (tmp_path / "1.md").exists()
    text = (tmp_path / "TT-7.md").read_text(encoding="utf-8")
    assert "id: TT-7\nproject: alpha\n" in text
    assert text.endswith("## Цель\n\nтекст\n")
    with pytest.raises(NotFound):
        store.get("1")


def test_update_id_to_taken_or_bad_id_raises(tmp_path):
    """Занятый id (без учёта регистра), имя устройства Windows и путь отклоняются, файл не меняется."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Первая", task_id="abc")
    store.create("alpha", "Вторая")

    (tmp_path / "notes.md").write_text("заметка", encoding="utf-8")

    for bad in ("ABC", "con", "../x", "a b", "notes"):
        with pytest.raises(TaskError):
            store.update("1", new_id=bad)
    assert [t.id for t in store.tasks()] == ["1", "abc"]
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "заметка"


def test_tasks_skip_files_without_own_id(tmp_path):
    """Файл с именем не номером читается задачей, только если во frontmatter тот же id."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Своя")
    (tmp_path / "README.md").write_text("заметка", encoding="utf-8")
    (tmp_path / "01.md").write_text("---\ntitle: с нулём\n---\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("---\nid: other\n---\n", encoding="utf-8")
    (tmp_path / "login.md").write_text("---\nid: login\nproject: alpha\n---\n", encoding="utf-8")

    assert [t.id for t in store.tasks()] == ["1", "login"]


def test_create_with_bad_project_name_raises(tmp_path):
    """Имя проекта с заглавными буквами или пробелом отклоняется и при создании, и при переносе."""
    store = Store(tmp_path, git=False)
    with pytest.raises(TaskError):
        store.create("Alpha Beta", "Задача")
    store.create("alpha", "Задача")
    with pytest.raises(TaskError):
        store.update("1", project="../x")
    assert store.get("1").project == "alpha"


def test_bad_task_id_raises_task_error(tmp_path):
    """Id не номер (путь, имя) отклоняется до обращения к диску."""
    with pytest.raises(TaskError):
        Store(tmp_path, git=False).get("../1")


def test_move_to_unknown_status_raises(tmp_path):
    """Перевод в статус вне списка отклоняется и файл не меняет."""
    store = Store(tmp_path, git=False)
    store.create("alpha", "Задача")

    with pytest.raises(TaskError):
        store.move("1", "wip")
    assert store.get("1").status == "backlog"


def test_get_missing_task_raises_not_found(tmp_path):
    """Чтение несуществующей задачи - NotFound."""
    with pytest.raises(NotFound):
        Store(tmp_path, git=False).get("1")


@pytest.mark.skipif(shutil.which("git") is None, reason="git не установлен")
def test_each_write_is_a_git_commit(tmp_path):
    """Создание, перевод, перенос и комментарий - по коммиту в git каталога данных."""
    store = Store(tmp_path, git=True)

    store.create("alpha", "Задача", author="kb")
    store.move("1", "doing", author="kb")
    store.update("1", project="beta", author="kb")
    store.comment("1", "взял", author="kb")
    store.update("1", new_id="named", author="kb")

    log = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "--format=%s"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.splitlines()
    tracked = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.split()
    assert tracked == ["named.md"]
    assert log == [
        "kb: правка #1, id 1 -> named",
        "kb: комментарий к #1",
        "kb: правка #1, проект alpha -> beta",
        "kb: #1 backlog -> doing",
        "kb: создана #1 в alpha - Задача",
    ]


def test_write_without_git_still_saves(tmp_path, monkeypatch):
    """Без git задача всё равно сохраняется: история не отменяет запись."""
    def no_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(history, "_git", no_git)

    task = Store(tmp_path, git=True).create("alpha", "Задача")

    assert (tmp_path / f"{task.id}.md").is_file()
