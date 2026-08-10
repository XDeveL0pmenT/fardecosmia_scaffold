# Fardecosmia Django scaffold

Каркас кампаний, кастомных пользователей, персонажей, мира/погоды и будущего
Roll20 bridge для **D&D 5E Classic / Legacy D&D 5E (2014)**.

## Важно до первой миграции

Проект уже использует собственную модель пользователя:

```python
AUTH_USER_MODEL = "accounts.User"
```

Не запускай первые миграции со стандартным `auth.User`, если собираешься использовать
этот каркас. Роли игрока и мастера НЕ находятся в `User`: они задаются отдельно через
`CampaignMembership` для каждой кампании.

## 1. Установка

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Первая проверка и миграции

```bash
python manage.py check
python manage.py makemigrations accounts campaigns characters world roll20
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Открой:

- `http://127.0.0.1:8000/admin/`
- `http://127.0.0.1:8000/`

## 3. Минимальная настройка через Admin

1. Создай пользователя или используй superuser.
2. Создай Campaign.
3. Создай CampaignMembership для себя с ролью `gm`.
4. Создай несколько Region.
5. Создай Character.
6. Создай Roll20Connection для Campaign.

## 4. Выдать токен будущему расширению

Пока UI для выдачи токена не сделан. Используй Django shell:

```bash
python manage.py shell
```

```python
from integrations.roll20.models import Roll20Connection, Roll20DeviceToken
connection = Roll20Connection.objects.first()
device, raw_token = Roll20DeviceToken.issue(connection, "My Chrome")
print(raw_token)
```

Секрет показывается только один раз. В БД хранится только хеш.

## 5. Проверка API

```bash
curl http://127.0.0.1:8000/api/v1/roll20/ping/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Пример snapshot:

```json
{
  "protocol": 1,
  "event_id": "81d13374-5659-4826-8f80-cce47a4f0821",
  "mode": "snapshot",
  "game": {"id": "12345678"},
  "character": {
    "id": "-Nd123Example",
    "name": "Аэрин",
    "sheet": "dnd5e_2014"
  },
  "attributes": {
    "hp": {"current": "32", "max": "41"},
    "hp_temp": {"current": "5", "max": ""},
    "ac": {"current": "17", "max": ""},
    "strength": {"current": "14", "max": ""}
  }
}
```

POST на:

`/api/v1/roll20/sync/`

## Архитектурные правила для Codex/PyCharm

В корне есть `AGENTS.md`. Codex читает его и получает устойчивый контекст проекта:
кастомного пользователя, роли кампании, правила Roll20-синхронизации и устройство
симуляции мира.

Архитектура объективных карт, 16 биомов и опциональной глобальной атмосферной
сетки описана в [`docs/WEATHER_SYSTEM.md`](docs/WEATHER_SYSTEM.md).

## Важно

- `config/urls.py` импортирует и `include`, и `path`.
- SQLite используется только для быстрого старта. Позже переключимся на PostgreSQL.
- Сырые Roll20 attributes сохраняются полностью, а нормализованные данные отдельно.
- `delta` обновляет только переданные attributes; `snapshot` заменяет полный сырой снимок.
- Пока синхронизация только Roll20 -> Django. `Roll20Command` оставлен под будущий
  Django -> browser extension -> Roll20.
