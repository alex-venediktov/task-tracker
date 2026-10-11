# Файлы пакета, не являющиеся .py, попадают в wheel и образ только через package-data

**тип:** ограничение · **предмет:** упаковка статики пакета · **этапы:** plan, implement, unit-tests

**вывод:** setuptools с `packages.find` кладёт в wheel только модули Python; HTML, CSS и JS из
`tracker/web/` без `[tool.setuptools.package-data]` в него не входят. Тесты и дымовой запуск этого не
видят: при `pip install -e` пакет читается из исходного каталога, и файлы на месте. Пропуск проявляется
только в образе, где Dockerfile ставит пакет `pip install .`. Проверка - собрать wheel
(`pip wheel --no-deps -w <каталог> .`) и перечислить содержимое `python -m zipfile -l`.

**источник:**
- `pyproject.toml:28` - `tracker = ["web/*"]`

**связи:** [[fastapi-root-mount-last]]
