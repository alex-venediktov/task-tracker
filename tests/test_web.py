"""Канбан-доска: страница и статика отдаются рядом с REST и MCP."""

import re

import pytest
from fastapi.testclient import TestClient

from tracker.app import create_app
from tracker.config import Settings


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, public_url="", git=False, port=8113)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_root_returns_board_page(client):
    """Корень службы отдаёт страницу доски, а не уходит в смонтированное MCP-приложение."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/static/board.js" in response.text


def test_page_references_only_served_static_files(client):
    """Каждый файл, на который ссылается страница, отдаётся из /static."""
    page = client.get("/").text
    assets = re.findall(r'"/static/([^"]+)"', page)

    assert sorted(assets) == ["board.css", "board.js"]
    for name in assets:
        assert client.get(f"/static/{name}").status_code == 200


def test_missing_static_file_returns_404(client):
    """Неизвестный файл статики - 404 доски, а не ответ MCP-приложения."""
    assert client.get("/static/nope.js").status_code == 404


def test_markdown_renders_tables_and_escapes_raw_html(client):
    """Предпросмотр рисует таблицу, а сырой html и ссылку javascript: из текста не исполняет."""
    text = "## Цель\n\n|a|b|\n|-|-|\n|1|2|\n\n<script>alert(1)</script> [x](javascript:alert(1))"

    html = client.post("/api/markdown", json={"text": text}).json()["html"]

    assert "<h2>Цель</h2>" in html
    assert "<table>" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html


def test_api_next_to_board_keeps_working(client):
    """REST с доской рядом отвечает: статусы для колонок и пустой список проекта без задач."""
    assert [s["status"] for s in client.get("/api/statuses").json()] == [
        "backlog",
        "todo",
        "doing",
        "review",
        "done",
    ]
    assert client.get("/api/tasks?project=fresh").json() == []
