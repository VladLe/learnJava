# Модель данных

БД хранит состояние конвейера, чтобы шаги были идемпотентны и устойчивы к сбоям.
Ниже — таблицы и диаграмма статусов обработки. DDL приведён в диалекте,
совместимом с SQLite (dev) и PostgreSQL (prod); финальные миграции — через
Alembic.

## Таблицы

### `sources` — источники новостей

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | Внутренний id |
| `slug` | text, unique | Человекочитаемый ключ (`techcrunch`) |
| `type` | text | Тип источника (`rss`) |
| `url` | text | URL ленты |
| `enabled` | bool | Активен ли источник |
| `fetch_interval_minutes` | int | Период опроса |
| `target_site_id` | FK → target_sites | Куда публиковать по умолчанию |
| `last_fetched_at` | timestamp, null | Когда опрашивали в последний раз |
| `created_at` | timestamp | — |

### `target_sites` — сайты WordPress

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `slug` | text, unique | Ключ сайта (`blog_main`) |
| `base_url` | text | Базовый URL сайта |
| `auth_user` | text | Логин WordPress |
| `auth_app_password_env` | text | Имя env-переменной с паролем приложения |
| `default_status` | text | `draft` / `publish` |
| `default_category_id` | int, null | Рубрика по умолчанию |
| `enabled` | bool | — |

> Сам пароль в БД не хранится — только имя env-переменной. Секрет читается из
> окружения в рантайме.

### `articles` — исходные статьи и их состояние

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `source_id` | FK → sources | Откуда пришла |
| `guid` | text | id элемента из ленты |
| `source_url` | text | Ссылка на оригинал |
| `url_hash` | text, unique | SHA-256 от нормализованного URL — ключ дедупликации |
| `original_title` | text | Заголовок оригинала |
| `original_summary` | text, null | Анонс из ленты |
| `full_text` | text, null | Извлечённый полный текст |
| `published_at` | timestamp, null | Дата публикации в источнике |
| `fetched_at` | timestamp | Когда мы её получили |
| `status` | text | Статус обработки (см. ниже) |
| `error` | text, null | Текст последней ошибки |

Индексы: `url_hash` (unique), `(status)`, `(source_id, published_at)`.

### `rewritten_content` — результат рерайта

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `article_id` | FK → articles, unique | Одна переписанная версия на статью |
| `title` | text | Новый заголовок |
| `body_html` | text | Тело поста в HTML |
| `excerpt` | text | Краткое описание |
| `seo_title` | text | SEO-заголовок |
| `seo_description` | text | SEO-описание |
| `tags` | json | Список тегов |
| `provider` | text | `anthropic` / `openai` |
| `model` | text | Модель генерации |
| `input_tokens` | int | Токены ввода (для учёта затрат) |
| `output_tokens` | int | Токены вывода |
| `created_at` | timestamp | — |

### `publications` — факты публикации

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `article_id` | FK → articles | Какая статья |
| `target_site_id` | FK → target_sites | На какой сайт |
| `wp_post_id` | int, null | ID поста в WordPress |
| `wp_url` | text, null | URL опубликованного поста |
| `status` | text | `published` / `failed` |
| `error` | text, null | Ошибка публикации |
| `published_at` | timestamp, null | Когда опубликовано |

Уникальность `(article_id, target_site_id)` — защита от повторной публикации
одной статьи на один и тот же сайт.

## Диаграмма статусов обработки

Поле `articles.status` отражает положение статьи в конвейере:

```
   fetched ──▶ extracted ──▶ rewritten ──▶ published
      │            │             │
      └────────────┴─────────────┴──────────▶ failed
                                                 │
                                          (ручной разбор
                                           или авто-ретрай)

   (дубликат на входе)  ──▶ skipped
```

| Статус | Значение | Кто переводит дальше |
|---|---|---|
| `fetched` | Получена из ленты, текст ещё не извлечён | шаг извлечения |
| `extracted` | Полный текст извлечён | шаг рерайта |
| `rewritten` | Текст переписан, есть `rewritten_content` | шаг публикации |
| `published` | Опубликована, есть запись в `publications` | терминальный |
| `failed` | Ошибка на одном из шагов, причина в `error` | ретрай / человек |
| `skipped` | Отброшена как дубликат на входе | терминальный |

Поскольку каждый шаг выбирает статьи по конкретному статусу, конвейер можно
запускать и перезапускать частями: например, прогнать только статьи в статусе
`rewritten`, если публикация ранее упала из-за недоступности сайта.

## Дедупликация

Ключ — `articles.url_hash` = `sha256(normalize(source_url))`, где нормализация
убирает UTM-метки, якоря и хвостовые слеши. Перед созданием статьи проверяем
наличие хеша; если есть — материал помечается `skipped` (или просто
пропускается). Дополнительно учитываем `guid` из ленты как вторичный признак.
