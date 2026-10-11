"""MCP по HTTP на /mcp: адрес машины в Host, проект подключения из заголовка, постановка текстом."""

import json

import pytest
from fastapi.testclient import TestClient

from tracker.app import create_app
from tracker.config import Settings

LAN = "http://192.0.2.10:8113"


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path, public_url=LAN, git=False, port=8113)
    with TestClient(create_app(settings), base_url=LAN) as test_client:
        yield test_client


def rpc(client, method, params=None, project=None):
    headers = {"Accept": "application/json, text/event-stream"}
    if project:
        headers["X-Project"] = project
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    response = client.post("/mcp", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def call(client, tool, arguments, project=None):
    result = rpc(client, "tools/call", {"name": tool, "arguments": arguments}, project)["result"]
    return result


def payload(result):
    structured = result.get("structuredContent")
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(result["content"][0]["text"])


def test_initialize_and_tools_list_pass_with_lan_host(client):
    """initialize и tools/list проходят при Host с адресом машины в локальной сети."""
    init = rpc(client, "initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    })
    tools = rpc(client, "tools/list")

    assert init["result"]["serverInfo"]["name"] == "task-tracker"
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert names == {
        "list_projects", "list_tasks", "get_task", "create_task",
        "update_task", "move_task", "comment_task",
    }


def test_create_task_into_neighbour_project_records_author(client, tmp_path):
    """Подключение проекта alpha ставит задачу в beta: во frontmatter проект beta, автор alpha."""
    result = call(client, "create_task", {"title": "Соседу", "project": "beta"}, project="alpha")

    assert payload(result)["project"] == "beta"
    text = (tmp_path / "1.md").read_text(encoding="utf-8")
    assert "author: alpha" in text


def test_create_task_without_project_goes_to_own_project(client):
    """Без project задача встаёт в проект, названный заголовком X-Project."""
    result = call(client, "create_task", {"title": "Себе"}, project="alpha")

    assert payload(result)["project"] == "alpha"


def test_create_task_without_any_project_is_error(client):
    """Ни project, ни заголовка - ошибка инструмента с объяснением, задача не создаётся."""
    result = call(client, "create_task", {"title": "Никуда"})

    assert result["isError"] is True
    assert "X-Project" in result["content"][0]["text"]


def test_move_to_unknown_status_explains_error(client):
    """Ошибка хранилища доходит до модели своим текстом, а не обезличенной."""
    call(client, "create_task", {"title": "Задача"}, project="alpha")

    result = call(client, "move_task", {"task_id": "1", "status": "wip"})

    assert result["isError"] is True
    assert "wip" in result["content"][0]["text"]


def test_get_task_markdown_returns_file_text(client, tmp_path):
    """get_task с markdown=true отдаёт исходный md-файл задачи текстом."""
    call(client, "create_task", {"title": "Постановка", "body": "## Цель\n\nтекст"}, project="alpha")

    result = call(client, "get_task", {"task_id": "1", "markdown": True})

    expected = (tmp_path / "1.md").read_text(encoding="utf-8")
    assert result["content"][0]["text"] == expected


def test_update_task_moves_task_to_other_project(client):
    """update_task с project переносит задачу: номер прежний, list_tasks нового проекта её видит."""
    call(client, "create_task", {"title": "Задача", "tags": ["ui"]}, project="alpha")

    moved = payload(call(client, "update_task", {"task_id": "1", "project": "beta"}, project="alpha"))
    found = payload(call(client, "list_tasks", {"project": "beta", "tag": "ui"}))

    assert (moved["id"], moved["project"]) == ("1", "beta")
    assert [t["id"] for t in found] == ["1"]
