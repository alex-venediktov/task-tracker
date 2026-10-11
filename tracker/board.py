"""Канбан-доска: страница и её статика из каталога tracker/web, данные - через REST."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt
from pydantic import BaseModel

WEB_DIR = Path(__file__).parent / "web"

# Сырой html из текста экранируется, ссылки javascript: не создаются.
MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


class MarkdownIn(BaseModel):
    text: str = ""


def render_markdown(text: str) -> str:
    return MARKDOWN.render(text)


def mount_board(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    def board() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")

    @app.post("/api/markdown")
    def markdown(data: MarkdownIn) -> dict:
        return {"html": render_markdown(data.text)}

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
