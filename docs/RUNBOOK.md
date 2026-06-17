# RUNBOOK — боевой запуск

Пошаговая инструкция: от пустого сервера до публикации новостей в WordPress.
Команды даны для двух вариантов развёртывания — напрямую (Python) и через
Docker. Выбери один.

> Принцип безопасного старта: сначала всё в черновики (`draft`) и/или с ручной
> модерацией, оцениваешь качество рерайта, и только потом включаешь
> автопубликацию.

---

## 0. Что понадобится

- Сервер с Python 3.11+ (или Docker).
- **Сайт на WordPress** с доступом к REST API по HTTPS.
- **Ключ LLM**: `ANTHROPIC_API_KEY` (по умолчанию) или `OPENAI_API_KEY`.
- (Опционально) **ключ Pexels** для изображений записи.
- Хотя бы одна **RSS-лента**, чьи страницы статей реально открываются ботом
  (некоторые крупные СМИ блокируют автоматические запросы — см. §9).

---

## 1. Подготовка WordPress

1. Войди в админку WordPress под пользователем, от имени которого будут
   публиковаться посты (роль **Author** или выше; для записи в любые рубрики —
   **Editor**/**Administrator**).
2. **Пользователи → Профиль → Application Passwords** (Пароли приложений).
   Введи имя (например `news-rewriter`) и нажми **Add New Application Password**.
3. Скопируй выданный пароль (вид `xxxx xxxx xxxx xxxx xxxx xxxx`). Это и есть
   `auth_app_password`. Показывается один раз — сохрани.
4. Проверка вручную (необязательно):
   ```bash
   curl -u "ЛОГИН:ПАРОЛЬ ПРИЛОЖЕНИЯ" https://ваш-сайт/wp-json/wp/v2/users/me
   ```
   Должен вернуться JSON твоего пользователя.

> Application Passwords встроены в WordPress с версии 5.6 и работают по HTTPS.
> Плагины не нужны. Если эндпоинт `/wp-json/` отдаёт 404 — включи «красивые»
> постоянные ссылки (Настройки → Постоянные ссылки) и проверь, что REST API не
> отключён плагином безопасности.

---

## 2. Установка

### Вариант A — напрямую (Python)

```bash
git clone <репозиторий> && cd <репозиторий>
python -m venv .venv && source .venv/bin/activate
pip install -e ".[prod]"        # gunicorn + psycopg для прода
```

### Вариант B — Docker

```bash
git clone <репозиторий> && cd <репозиторий>
# .env заполняется на шаге 3, затем:
docker compose up --build -d
```

В compose поднимаются три сервиса: `db` (PostgreSQL), `web` (gunicorn) и
`scheduler`. Миграции и сбор статики делает `web` при старте; `scheduler` их не
повторяет.

---

## 3. Конфигурация `.env`

Скопируй шаблон и заполни:

```bash
cp .env.example .env
```

Сгенерируй секреты:

```bash
# Ключ шифрования паролей WordPress (обязателен!)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Секретный ключ Django
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Минимальный боевой `.env`:

```ini
SECRET_KEY=<сгенерированный>
DEBUG=False
ALLOWED_HOSTS=ваш-домен,localhost

# Прямой запуск (SQLite) ИЛИ Docker (PostgreSQL):
DATABASE_URL=sqlite:///db.sqlite3
# DATABASE_URL=postgres://newsroom:newsroom@db:5432/newsroom

FIELD_ENCRYPTION_KEY=<сгенерированный Fernet-ключ>

REWRITE_PROVIDER=anthropic
ANTHROPIC_API_KEY=<ваш ключ>
ANTHROPIC_MODEL=claude-opus-4-8

# Опционально — изображения записи:
IMAGE_PROVIDER=none
PEXELS_API_KEY=
```

> `FIELD_ENCRYPTION_KEY` нельзя менять после того, как в БД сохранены пароли
> WordPress — иначе их нельзя будет расшифровать. Храни его так же бережно, как
> и сами пароли.

---

## 4. Инициализация БД и администратора

**Вариант A (Python):**
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000   # для теста; в проде — gunicorn
```

**Вариант B (Docker):**
```bash
docker compose exec web python manage.py createsuperuser
```

Открой `/admin` и войди под созданным суперюзером.

---

## 5. Настройка в админке

### 5.1 Добавить сайт WordPress

**Newsroom → Target sites → Добавить**:

| Поле | Значение |
|---|---|
| `name` | Любое понятное имя |
| `base_url` | `https://ваш-сайт` (без `/wp-json`) |
| `auth_user` | Логин WordPress |
| `auth_app_password` | Пароль приложения из §1 |
| `default_status` | `draft` (на старте!) |
| `enabled` | да |

Сохрани. Затем выдели сайт в списке и выполни действия из выпадающего меню:

1. **«Проверить подключение к WordPress»** — должно быть «подключение успешно».
2. **«Синхронизировать рубрики с WordPress»** — подтянет категории сайта
   (нужно, чтобы выбрать рубрику у ленты).

### 5.2 Добавить RSS-ленту

**Newsroom → Sources → Добавить**:

| Поле | Значение |
|---|---|
| `name` | Имя источника |
| `url` | URL RSS-ленты |
| `target_site` | Выбранный сайт |
| `target_category` | Рубрика (список отфильтрован по сайту; появляется после синхронизации рубрик) |
| `fetch_interval_minutes` | Период опроса, напр. `60` |
| `tone` | `neutral` / `analytical` / `conversational` |
| `target_length` | `short` / `medium` / `long` |
| `add_featured_image` | Подбирать ли картинку (если настроен `IMAGE_PROVIDER`) |
| `require_moderation` | **да** на старте — статьи будут ждать одобрения |
| `enabled` | да |

---

## 6. Префлайт

Перед первым прогоном проверь все интеграции:

```bash
python manage.py doctor          # БД, шифрование, RSS, извлечение, WP, картинки, LLM-ключ
python manage.py doctor --llm    # + крошечный тестовый рерайт (тратит немного токенов)
```
*(в Docker: `docker compose exec web python manage.py doctor --llm`)*

Добивайся, чтобы строки были `OK` (или `—` для отключённого). Если что-то
`FAIL` — см. §9.

---

## 7. Первый боевой прогон (один источник)

```bash
python manage.py run_pipeline --source-id <ID источника>
```

Команда пройдёт по шагам: сбор → дедуп → извлечение → рерайт → (если включена
модерация) ожидание. Смотри сводку по шагам в выводе.

Проверь результат в админке:

- **Newsroom → Articles** — фильтр по статусу. С модерацией статьи будут в
  статусе `pending`.
- Открой `RewrittenContent` соответствующей статьи — оцени заголовок, тело,
  SEO-поля, теги.
- Если устраивает: выдели статьи `pending` → действие **«Одобрить»** →
  они перейдут в `rewritten`.
- Запусти публикацию: `python manage.py run_pipeline --step publish --source-id <ID>`.
- В WordPress появится **черновик** в нужной рубрике (т.к. `default_status=draft`).
  Проверь его и опубликуй вручную, либо действием **«Опубликовать (снять с
  черновика)»** у `Publication` в админке.

Отклонить неудачный рерайт: действие **«Отклонить»** у статьи (→ `rejected`).

---

## 8. Перевод в боевой режим

Когда качество рерайта устраивает:

1. **Автопубликация.** У сайта (Target site) действие **«Включить
   автопубликацию»** (`default_status → publish`). Можно переопределить на
   уровне ленты полем `post_status`.
2. **Снять модерацию** (опционально). У источника убери `require_moderation` —
   статьи будут публиковаться без ручного одобрения.
3. **Запусти планировщик** — он сам опрашивает каждую ленту по её интервалу:
   ```bash
   python manage.py run_scheduler        # отдельный процесс
   ```
   В Docker сервис `scheduler` уже запущен. Для Варианта A оформи его как
   systemd-юнит или supervisor-процесс, чтобы переживал перезагрузки.

История запусков планировщика и расписание видны в админке
(**Django APScheduler → Django jobs / job executions**).

---

## 9. Диагностика типичных проблем

| Симптом | Причина и решение |
|---|---|
| `doctor` извлечение `FAIL`, `403/503` | Сайт-источник блокирует ботов. Поменяй `EXTRACT_USER_AGENT` в `.env`, либо выбери ленту с открытыми страницами / с полным текстом прямо в RSS. |
| `CERTIFICATE_VERIFY_FAILED` | TLS-перехват в сети (корпоративный прокси). Добавь корневой сертификат прокси в доверенные (`SSL_CERT_FILE`) на сервере. |
| WP `401/403` | Неверный логин или пароль приложения; у пользователя не хватает прав на рубрику; REST API закрыт плагином безопасности. |
| WP `Name or service not known` | Опечатка в `base_url` или сайт недоступен с сервера. |
| LLM `FAIL: ключ не задан` | Не заполнен `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` или не совпадает `REWRITE_PROVIDER`. |
| Картинки не ставятся | `IMAGE_PROVIDER=none` или пустой `PEXELS_API_KEY`; у ленты выключен `add_featured_image`. Сбой подбора картинки **не** блокирует публикацию — пост выйдет без неё. |
| Дубликаты не публикуются повторно | Так и задумано: дедупликация по нормализованному URL. Уникальность `(article, target_site)` защищает от повторной публикации. |

Упавшие статьи (`failed`) можно перезапустить: выдели в админке → действие
**«Повторить»** (вернёт в `fetched`).

---

## 10. Эксплуатация

- **Метрики**: страница `/admin/metrics/` — статьи по статусам, публикации,
  затраты токенов (всего и по модели), счётчики источников и сайтов.
- **Логи**: пишутся в stdout (в Docker — `docker compose logs -f web scheduler`).
- **Несколько сайтов и лент**: добавляются так же; у каждой ленты своя привязка
  «лента → рубрика конкретного сайта».
- **Стоимость**: следи за токенами на странице метрик. Для больших объёмов можно
  выбрать более дешёвую модель (`ANTHROPIC_MODEL=claude-sonnet-4-6` или
  `claude-haiku-4-5`) — рерайт не самая «тяжёлая» задача.

---

## Шпаргалка по командам

```bash
python manage.py doctor [--llm]                    # префлайт
python manage.py run_pipeline                       # все источники, все шаги
python manage.py run_pipeline --source-id <ID>      # один источник целиком
python manage.py run_pipeline --step fetch          # только сбор
python manage.py run_pipeline --step rewrite        # только рерайт
python manage.py run_pipeline --step publish        # только публикация
python manage.py run_scheduler                       # фоновый планировщик
```
