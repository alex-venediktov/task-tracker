"""REST службы: создание, сырой markdown, ручные правки, фильтры, перенос между проектами, коды ошибок."""

import pytest
from fastapi.testclient import TestClient

from tracker.app import create_app
from tracker.config import Settings


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, public_url="http://tt", git=False, port=8113)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def create(client, project="alpha", **fields):
    response = client.post("/api/tasks", json={"project": project, "title": "Задача", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_post_task_creates_file_and_raw_returns_same_text(client, tmp_path):
    """Задача из POST ложится файлом, а /t/<id>.md отдаёт этот файл как text/markdown."""
    task = create(client, title="Первая", body="текст")

    assert task["url"] == "http://tt/t/1.md"
    assert task["project"] == "alpha"
    raw = client.get("/t/1.md")
    assert raw.headers["content-type"].startswith("text/markdown")
    assert raw.text == (tmp_path / "1.md").read_text(encoding="utf-8")


def test_get_task_after_disk_edit_shows_new_title(client, tmp_path):
    """Файл, поправленный на диске, читается через REST без перезапуска службы."""
    create(client, title="Было")
    path = tmp_path / "1.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Было", "Стало"), encoding="utf-8")

    assert client.get("/api/tasks/1").json()["title"] == "Стало"


def test_move_changes_status_in_list(client):
    """Перевод меняет статус, и фильтр списка по статусу его видит."""
    create(client)
    client.post("/api/tasks/1/move", json={"status": "doing"})

    assert [t["id"] for t in client.get("/api/tasks?project=alpha&status=doing").json()] == ["1"]
    assert client.get("/api/projects").json()[0]["by_status"]["doing"] == 1


def test_patch_project_moves_task_between_projects(client):
    """PATCH проекта переносит задачу: номер и ссылка прежние, фильтр по проекту видит её в новом."""
    create(client)

    task = client.patch("/api/tasks/1", json={"project": "beta"}).json()

    assert (task["id"], task["project"], task["url"]) == ("1", "beta", "http://tt/t/1.md")
    assert client.get("/api/tasks?project=alpha").json() == []
    assert [t["id"] for t in client.get("/api/tasks?project=beta").json()] == ["1"]


def test_patch_id_renames_task_and_old_link_is_gone(client):
    """PATCH id переименовывает задачу: новая ссылка отдаёт файл, прежняя - 404; занятый id - 400."""
    create(client)
    create(client, id="busy")

    task = client.patch("/api/tasks/1", json={"id": "login-form"}).json()

    assert (task["id"], task["url"]) == ("login-form", "http://tt/t/login-form.md")
    assert client.get("/t/login-form.md").status_code == 200
    assert client.get("/t/1.md").status_code == 404
    assert client.patch("/api/tasks/login-form", json={"id": "BUSY"}).status_code == 400


def test_tag_filter_and_tag_list(client):
    """Фильтр по метке отбирает задачи с ней; список меток считает задачи и сужается проектом."""
    create(client, tags=["ui"])
    create(client, tags=["api"])
    create(client, project="beta", tags=["ui"])

    assert [t["id"] for t in client.get("/api/tasks?tag=ui").json()] == ["1", "3"]
    assert client.get("/api/tags").json() == [{"tag": "api", "tasks": 1}, {"tag": "ui", "tasks": 2}]
    assert client.get("/api/tags?project=beta").json() == [{"tag": "ui", "tasks": 1}]


def test_empty_filters_return_all_tasks(client):
    """Пустые фильтры проекта, статуса и метки - все задачи, а не ошибка."""
    create(client)
    create(client, project="beta")

    assert len(client.get("/api/tasks?project=&status=&tag=").json()) == 2


def test_unknown_task_returns_404(client):
    """Несуществующая задача - 404 и в JSON, и в сыром markdown."""
    assert client.get("/api/tasks/9").status_code == 404
    assert client.get("/t/9.md").status_code == 404


def test_bad_status_returns_400(client):
    """Неизвестный статус при создании - 400 с объяснением."""
    response = client.post("/api/tasks", json={"project": "alpha", "title": "З", "status": "wip"})

    assert response.status_code == 400
    assert "wip" in response.json()["detail"]


def test_bad_project_in_patch_returns_400(client):
    """Неверное имя проекта при переносе - 400, задача остаётся в своём проекте."""
    create(client)

    assert client.patch("/api/tasks/1", json={"project": "Bad Name"}).status_code == 400
    assert client.get("/api/tasks/1").json()["project"] == "alpha"
