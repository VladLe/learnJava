from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from newsroom.extract.article import extract_text
from newsroom.images.factory import get_image_provider
from newsroom.models import Source, TargetSite
from newsroom.publish.wordpress import WordPressPublisher
from newsroom.sources.rss import RssFetcher


class Command(BaseCommand):
    help = "Preflight check: validate each external integration independently."

    def add_arguments(self, parser):
        parser.add_argument(
            "--llm", action="store_true",
            help="Also do a tiny real LLM rewrite call (consumes tokens)",
        )

    def handle(self, *args, **options):
        self.ok = True

        self._check("База данных", self._check_db)
        self._check("Ключ шифрования (FIELD_ENCRYPTION_KEY)", self._check_encryption_key)
        self._check("RSS-источники", self._check_rss)
        self._check("Извлечение текста", self._check_extract)
        self._check("Сайты WordPress", self._check_wordpress)
        self._check("Провайдер изображений", self._check_images)
        self._check("LLM-рерайтер", lambda: self._check_llm(options["llm"]))

        self.stdout.write("")
        if self.ok:
            self.stdout.write(self.style.SUCCESS("Все проверки пройдены."))
        else:
            self.stdout.write(self.style.WARNING("Есть проблемы — см. выше."))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _check(self, label, fn):
        try:
            msg = fn()
            self.stdout.write(f"  {self.style.SUCCESS('OK')}   {label}: {msg}")
        except _Skip as skip:
            self.stdout.write(f"  {self.style.WARNING('—')}    {label}: {skip}")
        except Exception as exc:
            self.ok = False
            self.stdout.write(f"  {self.style.ERROR('FAIL')} {label}: {exc}")

    def _check_db(self):
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return f"подключение к {connection.vendor}"

    def _check_encryption_key(self):
        if not getattr(settings, "FIELD_ENCRYPTION_KEY", ""):
            raise ValueError("не задан — пароли WordPress нельзя зашифровать")
        return "задан"

    def _check_rss(self):
        sources = list(Source.objects.filter(enabled=True))
        if not sources:
            raise _Skip("нет включённых источников")
        fetcher = RssFetcher()
        results = []
        for src in sources:
            items = fetcher.fetch(src)
            results.append(f"{src.name}: {len(items)} записей")
        return "; ".join(results)

    def _check_extract(self):
        sources = list(Source.objects.filter(enabled=True))
        if not sources:
            raise _Skip("нет источников для проверки")
        fetcher = RssFetcher()
        last_error = None
        for src in sources:
            items = fetcher.fetch(src)
            if not items:
                continue
            try:
                text = extract_text(items[0].url)
                return f"{len(text)} символов из «{src.name}»"
            except Exception as exc:
                last_error = exc
        if last_error:
            raise ValueError(f"ни один источник не отдал текст (последняя ошибка: {last_error})")
        raise _Skip("в лентах нет записей")

    def _check_wordpress(self):
        sites = list(TargetSite.objects.filter(enabled=True))
        if not sites:
            raise _Skip("нет включённых сайтов")
        results = []
        for site in sites:
            WordPressPublisher.check_connection(site)
            results.append(f"{site.name}: OK")
        return "; ".join(results)

    def _check_images(self):
        provider = get_image_provider()
        if provider is None:
            raise _Skip("отключён (IMAGE_PROVIDER=none)")
        candidate = provider.search("technology")
        return f"найдено фото: {bool(candidate)}"

    def _check_llm(self, do_call):
        provider = getattr(settings, "REWRITE_PROVIDER", "")
        key_attr = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        if not getattr(settings, key_attr, ""):
            raise ValueError(f"{key_attr} не задан")
        if not do_call:
            return f"провайдер {provider}, ключ задан (рерайт не вызывался; --llm для проверки)"

        from newsroom.rewrite.base import RewriteRequest
        from newsroom.rewrite.factory import get_rewriter

        result = get_rewriter().rewrite(RewriteRequest(
            title="Тестовый заголовок",
            body="Это короткий тестовый текст для проверки работы рерайтера.",
            source_url="https://example.com/test",
        ))
        return f"{result.provider}/{result.model}, токены {result.input_tokens}+{result.output_tokens}"


class _Skip(Exception):
    """Raised for checks that are not applicable / not configured."""
