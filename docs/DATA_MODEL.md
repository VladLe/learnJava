# Модель данных

БД хранит и настройки (из админ-панели), и состояние конвейера. Модели описаны
как Django-модели; миграции — штатные Django. Ниже — таблицы и диаграмма статусов
обработки.

## Администратор и доступ

Отдельная таблица под админа не нужна — используется **встроенная модель
пользователя Django** (`auth_user`) и её система прав:

- **Администратор** — суперюзер (`is_superuser=True`), создаётся командой
  `createsuperuser`, имеет полный доступ к админке `/admin`.
- **Сотрудники** — при необходимости добавляются как staff-пользователи с
  ограниченными правами через группы Django.

Свою аутентификацию не пишем — это даёт Django auth.

## Таблицы

### `TargetSite` — сайты WordPress

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `name` | CharField | Человекочитаемое имя сайта |
| `base_url` | URLField | Базовый URL сайта |
| `auth_user` | CharField | Логин WordPress |
| `auth_app_password` | EncryptedCharField | Пароль приложения WP, **шифруется в БД** |
| `default_status` | CharField | `draft` / `publish` |
| `enabled` | BooleanField | Активен ли сайт |
| `created_at` | DateTimeField | — |

Пароль приложения вводится администратором в админке и хранится зашифрованным
(`django-encrypted-model-fields`, ключ `FIELD_ENCRYPTION_KEY` из окружения).

### `WordPressCategory` — рубрики, синхронизированные с сайта

Заполняется действием «Синхронизировать рубрики» в админке (тянет
`GET /wp-json/wp/v2/categories` с сайта). Нужна, чтобы у RSS-ленты можно было
выбрать целевую рубрику из списка, а не вводить числом.

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | Внутренний id |
| `site` | FK → TargetSite | Какому сайту принадлежит рубрика |
| `wp_category_id` | IntegerField | ID категории в самом WordPress |
| `name` | CharField | Название рубрики |
| `slug` | CharField | Slug рубрики |
| `synced_at` | DateTimeField | Когда синхронизировали |

Уникальность `(site, wp_category_id)`.

### `Source` — RSS-ленты

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `name` | CharField | Имя источника |
| `type` | CharField | Тип источника (`rss`) |
| `url` | URLField | URL ленты |
| `enabled` | BooleanField | Активен ли источник |
| `fetch_interval_minutes` | IntegerField | Период опроса |
| `target_site` | FK → TargetSite | Куда публиковать |
| `target_category` | FK → WordPressCategory, null | **В какую рубрику сайта** публиковать новости этой ленты |
| `post_status` | CharField, null | Переопределение статуса публикации (иначе берётся с сайта) |
| `tone` | CharField | Тон рерайта (`neutral`/`analytical`/`conversational`) |
| `target_length` | CharField | Длина рерайта (`short`/`medium`/`long`) |
| `add_featured_image` | BooleanField | Подбирать изображение записи из стокового банка |
| `require_moderation` | BooleanField | Требовать ручного одобрения перед публикацией |
| `last_fetched_at` | DateTimeField, null | Когда опрашивали последний раз |
| `created_at` | DateTimeField | — |

В админке поле `target_category` показывается выпадающим списком,
отфильтрованным по выбранному `target_site`.

### `Article` — исходные статьи и их состояние

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `source` | FK → Source | Откуда пришла |
| `guid` | CharField | id элемента из ленты |
| `source_url` | URLField | Ссылка на оригинал |
| `url_hash` | CharField, unique | SHA-256 от нормализованного URL — ключ дедупликации |
| `original_title` | CharField | Заголовок оригинала |
| `original_summary` | TextField, null | Анонс из ленты |
| `full_text` | TextField, null | Извлечённый полный текст |
| `published_at` | DateTimeField, null | Дата публикации в источнике |
| `fetched_at` | DateTimeField | Когда мы её получили |
| `status` | CharField | Статус обработки (см. ниже) |
| `error` | TextField, null | Текст последней ошибки |

Индексы: `url_hash` (unique), `status`, `(source, published_at)`.

### `RewrittenContent` — результат рерайта

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `article` | OneToOne → Article | Одна переписанная версия на статью |
| `title` | CharField | Новый заголовок |
| `body_html` | TextField | Тело поста в HTML |
| `excerpt` | TextField | Краткое описание |
| `seo_title` | CharField | SEO-заголовок |
| `seo_description` | TextField | SEO-описание |
| `tags` | JSONField | Список тегов |
| `provider` | CharField | `anthropic` / `openai` |
| `model` | CharField | Модель генерации |
| `input_tokens` | IntegerField | Токены ввода (учёт затрат) |
| `output_tokens` | IntegerField | Токены вывода |
| `created_at` | DateTimeField | — |

### `Publication` — факты публикации

| Поле | Тип | Описание |
|---|---|---|
| `id` | PK | — |
| `article` | FK → Article | Какая статья |
| `target_site` | FK → TargetSite | На какой сайт |
| `wp_post_id` | IntegerField, null | ID поста в WordPress |
| `wp_url` | URLField, null | URL опубликованного поста |
| `status` | CharField | `published` / `failed` |
| `error` | TextField, null | Ошибка публикации |
| `published_at` | DateTimeField, null | Когда опубликовано |

Уникальность `(article, target_site)` — защита от повторной публикации одной
статьи на один и тот же сайт.

> Историю запусков планировщика хранят модели `django-apscheduler`
> (`DjangoJob`, `DjangoJobExecution`) — отдельно проектировать не нужно, они
> идут с библиотекой и видны в админке.

## Диаграмма статусов обработки

Поле `Article.status` отражает положение статьи в конвейере:

```
                                  (если у ленты включена модерация)
                                   ┌─── pending ───┐
                                   │   одобрить ▲  │ отклонить
                                   │            │  ▼
   fetched ──▶ extracted ──▶ rewritten ──▶ published   rejected
      │            │             │
      └────────────┴─────────────┴──────────▶ failed
                                                 │
                                          («Повторить» в админке
                                           или авто-ретрай)

   (дубликат на входе)  ──▶ skipped
```

Если у источника включён флаг `require_moderation`, после рерайта статья уходит
в `pending` (а не сразу в `rewritten`) и ждёт ручного решения в админке:
действие «Одобрить» переводит её в `rewritten` (попадёт в публикацию на
следующем прогоне), «Отклонить» — в `rejected` (терминальный). Шаг публикации
по-прежнему выбирает только `rewritten`, поэтому неодобренные статьи не выходят.

| Статус | Значение | Кто переводит дальше |
|---|---|---|
| `fetched` | Получена из ленты, текст ещё не извлечён | шаг извлечения |
| `extracted` | Полный текст извлечён | шаг рерайта |
| `rewritten` | Текст переписан, есть `RewrittenContent` | шаг публикации |
| `pending` | Переписана, ждёт ручной модерации | человек (одобрить/отклонить) |
| `rejected` | Отклонена модератором | терминальный |
| `published` | Опубликована, есть запись в `Publication` | терминальный |
| `failed` | Ошибка на одном из шагов, причина в `error` | ретрай / человек |
| `skipped` | Отброшена как дубликат на входе | терминальный |

Поскольку каждый шаг выбирает статьи по конкретному статусу, конвейер можно
запускать и перезапускать частями: например, прогнать только статьи в статусе
`rewritten`, если публикация ранее упала из-за недоступности сайта.

## Дедупликация

Ключ — `Article.url_hash` = `sha256(normalize(source_url))`, где нормализация
убирает UTM-метки, якоря и хвостовые слеши. Перед созданием статьи проверяем
наличие хеша; если есть — материал помечается `skipped` (или просто
пропускается). Дополнительно учитываем `guid` из ленты как вторичный признак.
