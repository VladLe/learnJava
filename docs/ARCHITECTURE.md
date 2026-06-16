# Архитектура

## Обзор конвейера

```
                       ┌─────────────────────────────────────────────┐
                       │              Планировщик (APScheduler)        │
                       │   запускает конвейер по расписанию источника  │
                       └───────────────────────┬─────────────────────┘
                                               │
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │  Сбор    │──▶│ Дедупли- │──▶│Извлечение│──▶│  Рерайт  │──▶│Публикация│
   │  (RSS)   │   │  кация   │   │  текста  │   │  (LLM)   │   │   (WP)   │
   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
        │              │              │              │              │
        ▼              ▼              ▼              ▼              ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │                       База данных (состояние)                       │
   │  sources · target_sites · articles · rewritten_content · publications│
   └────────────────────────────────────────────────────────────────────┘
```

Каждый шаг читает статьи в определённом статусе, обрабатывает их и переводит в
следующий статус. Это делает конвейер **идемпотентным**: повторный запуск не
создаёт дублей и продолжает с того места, где остановился (см.
[DATA_MODEL.md](DATA_MODEL.md) — диаграмма статусов).

## Структура проекта

```
news_rewriter/
├── __init__.py
├── config.py              # загрузка настроек (pydantic-settings + YAML)
├── db.py                  # engine, session factory
├── models.py              # ORM-модели (см. DATA_MODEL.md)
│
├── sources/               # сбор новостей
│   ├── base.py            # интерфейс SourceFetcher
│   └── rss.py             # реализация на feedparser
│
├── extract/
│   └── article.py         # извлечение полного текста (trafilatura)
│
├── rewrite/               # абстракция рерайтера
│   ├── base.py            # RewriteService (ABC), RewriteRequest, RewriteResult
│   ├── anthropic.py       # AnthropicRewriter
│   ├── openai.py          # OpenAIRewriter
│   └── factory.py         # выбор провайдера по конфигу
│
├── publish/               # публикация
│   ├── base.py            # интерфейс Publisher
│   └── wordpress.py       # клиент WordPress REST API
│
├── pipeline.py            # оркестрация шагов fetch→dedup→extract→rewrite→publish
├── dedup.py               # логика дедупликации (хеш URL/guid)
├── scheduler.py           # регистрация задач APScheduler
└── cli.py                 # точка входа: run-once / run-scheduled / add-source

config/
├── settings.yaml          # источники и сайты (не секреты)
└── .env                   # секреты: ключи API, пароли WordPress

tests/
└── ...

alembic/                   # миграции БД
pyproject.toml
```

## Модули

### sources — сбор

`SourceFetcher` — интерфейс получения свежих материалов из источника.

```python
class FetchedItem:
    guid: str            # уникальный id из ленты
    url: str             # ссылка на оригинал
    title: str
    summary: str | None  # анонс из ленты
    published_at: datetime | None

class SourceFetcher(ABC):
    @abstractmethod
    def fetch(self, source: Source) -> list[FetchedItem]: ...
```

`RssFetcher` — реализация на `feedparser`. Возвращает элементы ленты; полный
текст добывается позже на шаге извлечения, потому что RSS обычно отдаёт только
анонс.

### extract — извлечение текста

`trafilatura` загружает страницу оригинала по URL и достаёт основной текст,
очищая навигацию, рекламу и комментарии. Если извлечь не удалось — статья
помечается статусом `failed` с причиной, конвейер продолжает работу с
остальными.

### rewrite — абстракция рерайтера

Ядро требования «сделать абстракцию». Контракт не зависит от провайдера:

```python
@dataclass
class RewriteRequest:
    title: str
    body: str
    source_url: str
    language: str = "ru"
    tone: str = "neutral"          # neutral | analytical | conversational
    target_length: str = "medium"  # short | medium | long

@dataclass
class RewriteResult:
    title: str
    body_html: str          # готовое тело поста (HTML)
    excerpt: str            # краткое описание
    seo_title: str
    seo_description: str
    tags: list[str]
    # метаданные генерации
    provider: str
    model: str
    input_tokens: int
    output_tokens: int

class RewriteService(ABC):
    @abstractmethod
    def rewrite(self, req: RewriteRequest) -> RewriteResult: ...
```

Реализации:

- **`AnthropicRewriter`** — официальный SDK `anthropic`. По умолчанию модель
  `claude-opus-4-8` (максимальное качество). Для высоких объёмов в конфиге можно
  выбрать более дешёвые `claude-sonnet-4-6` или `claude-haiku-4-5` — рерайт это
  не самая «тяжёлая» задача, и Sonnet/Haiku обычно хватает. Ответ запрашиваем в
  виде структурированного JSON (`output_config.format`), чтобы надёжно разобрать
  заголовок, тело и SEO-поля без хрупкого парсинга текста.
- **`OpenAIRewriter`** — альтернатива на GPT-моделях с тем же контрактом.

`factory.get_rewriter(config)` возвращает нужную реализацию по
`config.rewrite.provider`. Остальной код знает только про `RewriteService` —
смена провайдера не затрагивает конвейер.

**Промпт** инструктирует модель: переписать своими словами с сохранением фактов,
не выдумывать детали, оформить тело в HTML под WordPress, сгенерировать SEO-мета
и теги, в конце добавить атрибуцию со ссылкой на первоисточник.

### publish — публикация

`Publisher` — интерфейс публикации готового материала.

```python
class Publisher(ABC):
    @abstractmethod
    def publish(self, site: TargetSite, content: RewriteResult,
                source_url: str) -> PublishOutcome: ...
```

`WordPressPublisher` работает через **WordPress REST API**
(`POST /wp-json/wp/v2/posts`). Аутентификация — **Application Passwords**
(штатный механизм WP с версии 5.6): пара «логин + пароль приложения» по Basic
Auth поверх HTTPS, без плагинов. Поддерживаемые параметры: статус
(`draft`/`publish`), рубрика, теги, изображение записи (опционально). Возвращаем
ID и URL созданного поста для записи в `publications`.

> Альтернатива — старый XML-RPC, но REST API предпочтительнее: он современный,
> безопаснее и не требует включать XML-RPC (частый вектор атак).

### pipeline — оркестрация

`pipeline.py` связывает шаги и управляет переходами статусов в одной транзакции
на статью. Псевдокод:

```python
def run_source(source: Source) -> None:
    for item in fetcher.fetch(source):
        if dedup.is_seen(item):          # уже обрабатывали — пропуск
            continue
        article = store_article(item, status="fetched")
        try:
            article.full_text = extractor.extract(article.url)
            set_status(article, "extracted")

            result = rewriter.rewrite(to_request(article))
            store_rewritten(article, result)
            set_status(article, "rewritten")

            site = resolve_target_site(source)
            outcome = publisher.publish(site, result, article.url)
            store_publication(article, site, outcome)
            set_status(article, "published")
        except Exception as e:
            set_status(article, "failed", error=str(e))
```

Шаги намеренно разделены по статусам, чтобы их можно было запускать и
перезапускать независимо (например, повторить только публикацию для статей в
статусе `rewritten`).

### scheduler — расписание

`APScheduler` регистрирует по задаче на каждый включённый источник с его
интервалом (`fetch_interval`). Для старта достаточно in-process планировщика;
при росте нагрузки конвейер выносится в очередь задач (Celery + beat / RQ) без
изменения бизнес-логики.

## Конфигурация

Разделяем секреты и параметры:

- **`.env`** (через `pydantic-settings`) — секреты: `ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, пароли приложений WordPress, строка подключения к БД.
- **`config/settings.yaml`** — несекретная конфигурация: список источников,
  список целевых сайтов, какой источник в какой сайт публикует, выбор провайдера
  рерайта и модели.

Пример `settings.yaml`:

```yaml
rewrite:
  provider: anthropic        # anthropic | openai
  model: claude-opus-4-8
  tone: analytical
  target_length: medium

target_sites:
  - id: blog_main
    base_url: https://example.com
    auth_user: editor
    auth_app_password_env: WP_BLOG_MAIN_APP_PASSWORD
    default_status: draft     # draft на старте, publish — после проверки
    default_category_id: 5

sources:
  - id: techcrunch
    type: rss
    url: https://techcrunch.com/feed/
    enabled: true
    fetch_interval_minutes: 30
    target_site_id: blog_main
```

## Обработка ошибок и наблюдаемость

- **Ретраи** сетевых и LLM-вызовов с экспоненциальной задержкой (SDK Anthropic
  и `httpx` это умеют из коробки).
- **Идемпотентность** через статусы и уникальный хеш URL — повторный запуск
  безопасен.
- **Структурное логирование** каждого перехода статуса; ошибки сохраняются в
  поле `error` соответствующей записи.
- **Публикация в `draft`** по умолчанию на старте — даёт человеку проверить
  качество рерайта перед автопубликацией.
