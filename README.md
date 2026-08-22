# Фардекосмия

**Фардекосмия** — серверное Django-приложение для ведения настольных RPG-кампаний и симуляции живого фэнтезийного мира.

Проект объединяет кампании и роли Game Master / Player, глобальный канон и кампанийные переопределения, планетарный атлас, региональную погоду и атмосферную симуляцию, журнал значимых действий, запросы на одобрение, регистрацию с подтверждением email и приглашения в кампании.

Проект развивается как **Campaign OS / World Simulator**, а не только как энциклопедия лора.

---

## Технологии

- **Python 3.12+**
- **Django 5.2 LTS**
- **PostgreSQL** — целевая production-БД
- **SQLite** — локальный bootstrap и разработка
- **Server-rendered Django Templates**
- **Leaflet 1.9.4** — планетарный атлас
- Native JavaScript / ES modules

---

## Текущее состояние

Завершены основные foundation-этапы:

- `C1–C4.2` — атмосферная и климатическая симуляция;
- `R1` — погода регионов и lifecycle WeatherState;
- `M1` — Leaflet Planetary Atlas;
- `P1/P2` — Global Canon, Campaign Overrides и роли;
- `P3` — AuditLog;
- `P4` — ApprovalRequest;
- `P4.5` — Account Onboarding, Email Verification, Campaign Lifecycle & Membership.

Следующий этап:

```text
P5 — WorldEvent Foundation
```

Дальше по roadmap:

```text
CharacterKnowledge
M2 — Countries / Settlements / Roads / POI
Character / Roll20 integration surfaces
Ledger / Inventory / Purchases
Quests / Local Events
Player Map / Fog of War / Travel
Regional & Local Maps
C5+ climate development
```

---

## Что уже может обычный пользователь

После P4.5 пользователь может без Django Admin:

- зарегистрироваться;
- подтвердить email шестизначным кодом;
- восстановить пароль по email;
- создать собственную кампанию;
- автоматически стать её Game Master;
- получить приглашение в чужую кампанию;
- пройти регистрацию из приглашения;
- принять приглашение и стать Player;
- видеть доступные ему кампании.

Game Master дополнительно может:

- редактировать базовые данные кампании;
- приглашать игроков по email;
- отзывать приглашения;
- повышать Player до GM;
- понижать GM до Player;
- удалять участников;
- управлять кампанийными разделами согласно правам доступа.

В кампании всегда должен оставаться хотя бы один GM.

---

# Быстрый локальный запуск

## 1. Клонировать репозиторий

```bash
git clone <URL_РЕПОЗИТОРИЯ>
cd fardecosmia_scaffold
```

## 2. Создать виртуальное окружение

### Windows / PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Установить зависимости

Если в репозитории используется `requirements.txt`:

```bash
pip install -r requirements.txt
```

Если проект позже перейдёт на другой dependency manager, используйте актуальную инструкцию из репозитория.

## 4. Применить миграции

```bash
python manage.py migrate
```

## 5. Запустить сервер

```bash
python manage.py runserver
```

По умолчанию:

```text
http://127.0.0.1:8000/
```

---

# Email

Фардекосмия использует централизованный Django email backend.

Email уже используется для:

- подтверждения регистрации;
- восстановления пароля;
- приглашений в кампанию.

В будущем тот же фундамент сможет использоваться для transactional-уведомлений о событиях, запросах на одобрение и сессиях.

## Development mode

Без SMTP приложение может использовать Django Console Email Backend. В этом режиме письмо не отправляется в интернет — его содержимое появляется в терминале, где запущен `runserver`.

## SMTP / Gmail

Для реальной отправки писем задайте переменные окружения:

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
DJANGO_EMAIL_HOST=smtp.gmail.com
DJANGO_EMAIL_PORT=587

DJANGO_EMAIL_HOST_USER=your-address@gmail.com
DJANGO_EMAIL_HOST_PASSWORD=YOUR_APP_PASSWORD

DJANGO_EMAIL_USE_TLS=true
DJANGO_EMAIL_USE_SSL=false

DJANGO_EMAIL_TIMEOUT=10
DJANGO_DEFAULT_FROM_EMAIL=Фардекосмия <your-address@gmail.com>
```

Для Gmail используйте **Google App Password**, а не основной пароль аккаунта.

> Никогда не коммитьте пароль приложения, SMTP credentials или другие секреты в Git.

### Windows

Переменные можно задать:

- временно через PowerShell `$env:...`;
- постоянно через **Переменные среды пользователя Windows**;
- через конфигурацию запуска IDE.

После изменения системных переменных перезапустите PyCharm/терминал.

### Production

На хостинге те же значения задаются через Environment Variables / Secrets / Config Vars. Код Django менять не требуется.

---

# Проверка email-конфигурации

```bash
python manage.py shell -c "from django.conf import settings; print('BACKEND =', settings.EMAIL_BACKEND); print('HOST =', settings.EMAIL_HOST); print('PORT =', settings.EMAIL_PORT); print('USER =', settings.EMAIL_HOST_USER); print('TLS =', settings.EMAIL_USE_TLS); print('SSL =', settings.EMAIL_USE_SSL); print('FROM =', settings.DEFAULT_FROM_EMAIL)"
```

Для Gmail ожидается примерно:

```text
BACKEND = django.core.mail.backends.smtp.EmailBackend
HOST = smtp.gmail.com
PORT = 587
TLS = True
SSL = False
```

Пароль эта команда не выводит.

---

# Тесты

Полный suite:

```bash
python manage.py test --verbosity 1
```

Текущий baseline после P4.5:

```text
334 tests passed
4 PostgreSQL-only tests skipped on SQLite
```

Дополнительные проверки:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
```

PostgreSQL-only concurrency tests должны запускаться в PostgreSQL CI / production-like окружении.

---

# Архитектурные правила

## Пользователи и роли

Единственная user model:

```text
accounts.User
```

Она остаётся `AUTH_USER_MODEL`.

Нельзя добавлять глобальное поле вроде:

```text
User.role = GM
```

Роль существует только внутри кампании:

```text
CampaignMembership
├── PLAYER
└── GM
```

Один пользователь может быть GM в одной кампании и Player в другой.

## Минимум один GM

Активная Campaign не должна оставаться без Game Master.

Нельзя удалить или понизить последнего GM. Membership mutations должны проходить через domain services.

---

## Канон

Основная модель истины:

```text
Global Canon
    ↓
Campaign Override
    ↓
Effective Campaign Truth
    ↓
Character Knowledge / Player Visibility
```

Последний слой ещё развивается.

`WorldEntry` — универсальная лоровая статья, а не JSON-модель всего мира. Структурированные сущности вроде Settlement, Item, Race и Biome должны получать собственные модели, когда им нужна настоящая предметная структура.

---

## AuditLog

`AuditLog` хранит **значимые действия**, а не технические логи приложения.

Примеры:

```text
Создана кампания.
Игрок вступил в кампанию.
Регион изменён.
GM продвинул мировое время.
Campaign Override обновлён.
```

Не нужно писать AuditLog для:

- GET-запросов;
- каждого atmospheric timestep;
- каждого WeatherState;
- tile/hover/pan карты;
- login attempts;
- verification codes;
- password reset tokens.

Account/security logging и world/campaign audit — разные области.

---

## ApprovalRequest

ApprovalRequest — это безопасное зарегистрированное намерение:

```text
Request
↓
Pending
↓
Approve / Reject / Cancel
↓
Registered Domain Action
↓
AuditLog
```

Запрещено использовать payload как arbitrary command:

```json
{
  "model": "world.Region",
  "method": "delete"
}
```

Каждый production request type обязан проходить через whitelist handler и иметь человекочитаемый presenter.

`APPROVED` означает, что действие действительно успешно применено.

---

## Email security

Никогда не хранить plaintext:

- verification codes;
- campaign invite tokens;
- passwords;
- SMTP credentials;
- OAuth secrets;
- session secrets.

Email verification code хранится только в защищённом виде.

Campaign invitation использует high-entropy одноразовый token, а в БД сохраняется только защищённое представление.

---

# Campaign Invitations

Текущая модель приглашения:

```text
GM создаёт приглашение на email
↓
пользователь получает одноразовую ссылку
↓
login / registration
↓
email verification
↓
возврат к приглашению
↓
accept
↓
CampaignMembership = PLAYER
```

Приглашение:

- привязано к конкретному подтверждённому email;
- одноразовое;
- имеет срок действия;
- может быть отозвано GM;
- не требует ApprovalRequest;
- не хранит plaintext token в БД.

---

# Атмосфера и климат

Фардекосмия имеет собственную климатическую модель.

Она учитывает, среди прочего:

- движение по орбите;
- stellar forcing;
- наклон оси;
- SST;
- water vapor;
- облака;
- precipitation;
- orography;
- atmospheric circulation;
- terrain;
- Coriolis;
- региональную агрегацию погоды.

Region не является источником физики климата.

```text
AtmosphericGrid
↓
point sampling / area sampling
↓
Region weather / gameplay environment
```

Не добавляйте климатические костыли вроде:

```python
if biome == "desert":
    temperature += 8
```

Физические эффекты должны моделироваться через соответствующие процессы.

---

# Планетарный атлас

M1 использует Leaflet с пользовательской планетарной геометрией.

Важные свойства:

- equirectangular 2:1 global atlas;
- горизонтальный wrap;
- без latitude wrap;
- собственный радиус планеты;
- Region — редактируемый векторный контур;
- raster layers имеют собственный native zoom;
- глубокий zoom не создаёт фальшивую детализацию.

Архитектурно карты делятся на:

```text
Planet Atlas
↓
Regional Maps
↓
Local Maps
```

Города, дороги и POI в будущем должны быть структурированными/vector entities, а не навечно нарисованными на глобальной текстуре.

---

# Roll20

Roll20 остаётся источником истины для combat-sheet state.

Фардекосмия хранит:

```text
world state
campaign state
normalized Roll20 mirror
```

Нельзя привязывать персонажей Roll20 по имени. Используется explicit Roll20 character ID.

---

# Мировое время

Мировое время Campaign хранится в целых игровых минутах.

Продвижение времени проходит через domain service и является транзакционным.

Одно пользовательское продвижение времени создаёт одну высокоуровневую AuditLog-запись независимо от количества рассчитанных WeatherState/atmospheric шагов.

---

# Документация проекта

Перед крупными изменениями Coding Agent должен перечитать:

```text
AGENTS.md
WORLD_HANDOFF_v2.md
ARCHITECTURE_GUARDRAILS.md
MASTER_ROADMAP.md
```

Распределение ответственности:

```text
AGENTS.md
→ постоянные технические правила

WORLD_HANDOFF_v2.md
→ актуальное состояние мира и simulation/domain architecture

ARCHITECTURE_GUARDRAILS.md
→ архитектурные инварианты

MASTER_ROADMAP.md
→ направление разработки

Phase spec/report
→ конкретный текущий этап
```

---

# Стиль разработки

- domain services вместо тяжёлых views/models;
- server-rendered Django first;
- frontend framework только при реальной необходимости;
- permissions проверяются централизованно;
- campaign isolation обязательна;
- human-first UI;
- technical details вторичны;
- meaningful mutations аудируются;
- секреты не попадают в AuditLog;
- миграции проверяются до применения;
- новый функционал сопровождается regression tests.

---

# Human-first UI

Хорошо:

```text
GM одобрил запрос «Начать путешествие».
```

Плохо:

```text
approval_request.approved
payload_version=1
object_id=17
```

Raw JSON, UUID, internal enum и ContentType допустимы только как вторичная техническая диагностика.

---

# Безопасность

Не коммитьте:

```text
.env
SMTP password
Google App Password
SECRET_KEY
database password
OAuth tokens
Roll20 credentials
invite tokens
verification codes
```

Перед публикацией репозитория проверьте:

```bash
git status
```

и `.gitignore`.

Если секрет случайно попал в Git, недостаточно просто удалить строку — секрет нужно отозвать/сменить.

---

# Roadmap

```text
[x] P1/P2 — Canon / Overrides / Roles
[x] P3    — AuditLog
[x] P4    — ApprovalRequest
[x] P4.5  — Account / Email / Campaign Lifecycle

[ ] P5    — WorldEvent

[ ] CharacterKnowledge
[ ] M2 — Countries / Settlements / Roads / POI
[ ] Character / Roll20 surfaces
[ ] Ledger / Inventory / Purchases
[ ] Quests / Local Events
[ ] Player Map / Fog of War / Travel
[ ] Regional / Local Maps
[ ] C5+ climate development
```

---

## Статус

Проект находится в активной разработке.

Текущая версия уже содержит рабочий фундамент аккаунтов, кампаний, ролей, канона, аудита, approval workflows, планетарного атласа и физической симуляции атмосферы, но многие игровые подсистемы всё ещё находятся в roadmap.
