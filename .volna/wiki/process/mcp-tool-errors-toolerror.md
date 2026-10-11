# MCP SDK 2.x показывает модели текст исключения только у ToolError

**тип:** побочный эффект · **предмет:** ошибки MCP-инструментов · **этапы:** implement, unit-tests

**вывод:** исключение из тела инструмента, кроме `ToolError`, SDK заворачивает в `UnexpectedToolError`
с текстом «Error executing tool <имя>», а собственное сообщение оставляет в логе сервера
(`mcp/server/mcpserver/tools/base.py`, ветка `except Exception`). Модель получает `isError` без
объяснения и не может исправить вызов. Ошибки предметной области переводятся в `ToolError`
(`from mcp.server.mcpserver.exceptions import ToolError`) - тогда текст доходит до модели.

**источник:**
- `tracker/mcp_tools.py:42` - `raise ToolError(str(error)) from error`
- `tests/test_mcp.py:84` - `def test_move_to_unknown_status_explains_error(client):`

**связи:** [[mcp-host-check-loopback]]
