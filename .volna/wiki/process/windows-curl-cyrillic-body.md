# curl -d с кириллицей из Git Bash на Windows отправляет тело не в UTF-8

**тип:** ограничение · **предмет:** ручные HTTP-запросы · **этапы:** implement, unit-tests

**вывод:** строка с кириллицей в аргументе `curl -d '...'`, набранная в Git Bash на Windows, уходит
в системной кодировке, и JSON-сервер отвечает `Parse error: invalid unicode code point`. Ошибка
выглядит дефектом службы, хотя служба исправна. Тело с не-ASCII текстом передаётся файлом в UTF-8:
`curl --data-binary @body.json`.
