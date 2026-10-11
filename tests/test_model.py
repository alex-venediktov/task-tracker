"""Разбор и сборка md-файла задачи: frontmatter, незнакомые ключи, секция обсуждения."""

from tracker.model import Task, add_comment, parse, render


def test_render_then_parse_keeps_unknown_keys():
    """Незнакомые ключи frontmatter переживают сборку и разбор без изменений."""
    task = Task(id="1", project="a", title="Заголовок", extra={"order": 3, "owner": "kb"})

    again = parse(render(task), task_id="1")

    assert again.extra == {"order": 3, "owner": "kb"}
    assert again.title == "Заголовок"


def test_parse_without_frontmatter_takes_id_from_file():
    """Файл без frontmatter читается задачей в бэклоге с id из имени файла и телом целиком."""
    task = parse("Просто текст постановки\n", task_id="7")

    assert (task.id, task.title, task.status) == ("7", "#7", "backlog")
    assert task.body == "Просто текст постановки"


def test_parse_date_without_time_becomes_iso_string():
    """Дата без времени, вписанная руками, читается строкой ISO, а не объектом даты."""
    text = "---\ntitle: t\ncreated: 2026-10-11\n---\n"

    assert parse(text, task_id="1").created == "2026-10-11"


def test_parse_unknown_status_falls_back_to_backlog():
    """Статус вне списка, вписанный руками, читается как бэклог."""
    text = "---\ntitle: t\nstatus: wip\n---\n"

    assert parse(text, task_id="1").status == "backlog"


def test_add_comment_without_discussion_appends_section():
    """Первый комментарий заводит секцию обсуждения в конце тела."""
    body = add_comment("## Цель\n\nсделать", author="kb", when="2026-10-11 20:00", text="готово")

    assert body == "## Цель\n\nсделать\n\n## Обсуждение\n\n### 2026-10-11 20:00 - kb\n\nготово"


def test_add_comment_with_discussion_before_next_section_inserts_inside():
    """Комментарий встаёт в конец секции обсуждения, а следующая секция остаётся после него."""
    body = "## Обсуждение\n\n### 1 - a\n\nпервый\n\n## Готово, когда\n\nвсё"

    result = add_comment(body, author="b", when="2", text="второй")

    assert result == (
        "## Обсуждение\n\n### 1 - a\n\nпервый\n\n### 2 - b\n\nвторой\n\n## Готово, когда\n\nвсё"
    )
