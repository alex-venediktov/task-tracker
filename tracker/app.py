"""Сборка службы: REST, сырой markdown и MCP на /mcp в одном процессе."""

from __future__ import annotations

import contextlib

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tracker import config
from tracker.api import build_router
from tracker.board import mount_board
from tracker.mcp_tools import build_mcp
from tracker.model import TaskError
from tracker.store import NotFound, Store


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.load()
    store = Store(settings.data_dir, git=settings.git)
    mcp = build_mcp(store, settings)
    # Без проверки Host: ответ по адресу машины в частной сети (mcp/server/lowlevel/server.py:741).
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/mcp", host="0.0.0.0", stateless_http=True, json_response=True
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="task-tracker", lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings

    @app.exception_handler(TaskError)
    async def bad_request(_: Request, error: TaskError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(NotFound)
    async def not_found(_: Request, error: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=404)

    app.include_router(build_router(store, settings))
    mount_board(app)
    app.mount("/", mcp_app)
    return app


def run() -> None:
    import uvicorn

    settings = config.load()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
