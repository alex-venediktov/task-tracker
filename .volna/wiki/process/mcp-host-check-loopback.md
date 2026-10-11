# MCP SDK отклоняет запрос по адресу машины, если streamable_http_app собран с host по умолчанию

**тип:** ограничение · **предмет:** монтирование MCP в FastAPI · **этапы:** plan, implement

**вывод:** `MCPServer.streamable_http_app()` принимает `host="127.0.0.1"` по умолчанию, и для loopback
SDK сам включает проверку Host с разрешёнными только `127.0.0.1:*`, `localhost:*`, `[::1]:*`
(`mcp/server/lowlevel/server.py`, ветка `if transport_security is None and host in (...)`). Служба в
частной сети, смонтированная так, отвечает отказом на `Host: <адрес машины>:8113`. Сборка с явным
`host="0.0.0.0"` проверку не включает; без аутентификации это осознанный выбор для LAN.
Ловится тестом с `base_url` на адрес машины.

**источник:**
- `tracker/app.py:24` - `streamable_http_path="/mcp", host="0.0.0.0", stateless_http=True, json_response=True`
- `tests/test_mcp.py:43` - `def test_initialize_and_tools_list_pass_with_lan_host(client):`

**связи:** [[mcp-tool-errors-toolerror]]
