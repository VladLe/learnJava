import logging

from django import forms
from django.contrib import admin, messages
from django.http import JsonResponse
from django.urls import path

from .models import Article, Publication, RewrittenContent, Source, TargetSite, WordPressCategory
from .publish.wordpress import WordPressPublisher

logger = logging.getLogger(__name__)


# ── TargetSite ────────────────────────────────────────────────────────────────

@admin.register(TargetSite)
class TargetSiteAdmin(admin.ModelAdmin):
    list_display = ["name", "base_url", "default_status", "enabled", "created_at"]
    list_filter = ["enabled", "default_status"]
    search_fields = ["name", "base_url"]
    actions = [
        "action_check_connection",
        "action_sync_categories",
        "action_enable_autopublish",
        "action_disable_autopublish",
    ]

    @admin.action(description="Включить автопубликацию (статус по умолчанию → publish)")
    def action_enable_autopublish(self, request, queryset):
        n = queryset.update(default_status=TargetSite.Status.PUBLISH)
        self.message_user(request, f"Автопубликация включена для {n} сайтов.", messages.SUCCESS)

    @admin.action(description="Выключить автопубликацию (статус по умолчанию → draft)")
    def action_disable_autopublish(self, request, queryset):
        n = queryset.update(default_status=TargetSite.Status.DRAFT)
        self.message_user(request, f"Автопубликация выключена для {n} сайтов.", messages.SUCCESS)

    @admin.action(description="Проверить подключение к WordPress")
    def action_check_connection(self, request, queryset):
        for site in queryset:
            try:
                WordPressPublisher.check_connection(site)
                self.message_user(
                    request,
                    f"{site.name}: подключение успешно.",
                    messages.SUCCESS,
                )
            except Exception as exc:
                logger.exception("check_connection failed for %s", site.name)
                self.message_user(request, f"{site.name}: ошибка — {exc}", messages.ERROR)

    @admin.action(description="Синхронизировать рубрики с WordPress")
    def action_sync_categories(self, request, queryset):
        for site in queryset:
            try:
                n = WordPressPublisher.sync_categories(site)
                self.message_user(
                    request,
                    f"{site.name}: синхронизировано {n} рубрик.",
                    messages.SUCCESS,
                )
            except Exception as exc:
                logger.exception("sync_categories failed for %s", site.name)
                self.message_user(request, f"{site.name}: ошибка — {exc}", messages.ERROR)


# ── WordPressCategory ─────────────────────────────────────────────────────────

@admin.register(WordPressCategory)
class WordPressCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "site", "wp_category_id", "synced_at"]
    list_filter = ["site"]
    search_fields = ["name", "slug"]


# ── Source ────────────────────────────────────────────────────────────────────

class SourceAdminForm(forms.ModelForm):
    class Meta:
        model = Source
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Use site from POST data (user just changed it) or from the saved instance
        site_id = self.data.get("target_site") or (
            self.instance.target_site_id if self.instance.pk else None
        )
        if site_id:
            self.fields["target_category"].queryset = WordPressCategory.objects.filter(
                site_id=site_id
            )
        else:
            self.fields["target_category"].queryset = WordPressCategory.objects.none()


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    form = SourceAdminForm
    list_display = ["name", "url", "target_site", "target_category", "enabled", "last_fetched_at"]
    list_filter = ["enabled", "target_site", "tone", "target_length"]
    search_fields = ["name", "url"]
    actions = ["action_run_now"]

    class Media:
        js = ("newsroom/admin/source_admin.js",)

    @admin.action(description="Собрать сейчас (полный конвейер)")
    def action_run_now(self, request, queryset):
        from . import pipeline

        for source in queryset:
            try:
                result = pipeline.run_source(source)
                self.message_user(
                    request,
                    f"{source.name}: получено {result['fetched']}, "
                    f"опубликовано {result['published']}, ошибок {result['failed']}.",
                    messages.SUCCESS,
                )
            except Exception as exc:
                logger.exception("run_now failed for %s", source.name)
                self.message_user(request, f"{source.name}: ошибка — {exc}", messages.ERROR)

    def get_urls(self):
        return [
            path(
                "categories-by-site/",
                self.admin_site.admin_view(self.categories_by_site_view),
                name="newsroom_source_categories_by_site",
            ),
        ] + super().get_urls()

    def categories_by_site_view(self, request):
        site_id = request.GET.get("site_id", "")
        qs = (
            WordPressCategory.objects.filter(site_id=site_id).values("id", "name")
            if site_id
            else []
        )
        return JsonResponse({"categories": list(qs)})


# ── Article ───────────────────────────────────────────────────────────────────

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["original_title", "source", "status", "published_at", "fetched_at"]
    list_filter = ["status", "source"]
    search_fields = ["original_title", "source_url"]
    readonly_fields = ["url_hash", "fetched_at"]
    actions = ["action_retry"]

    @admin.action(description="Повторить обработку (вернуть статус fetched)")
    def action_retry(self, request, queryset):
        updated = queryset.filter(status=Article.Status.FAILED).update(
            status=Article.Status.FETCHED, error=""
        )
        level = messages.SUCCESS if updated else messages.WARNING
        self.message_user(request, f"Переведено в повтор: {updated} статей.", level)


# ── RewrittenContent ──────────────────────────────────────────────────────────

@admin.register(RewrittenContent)
class RewrittenContentAdmin(admin.ModelAdmin):
    list_display = ["article", "provider", "model", "input_tokens", "output_tokens", "created_at"]
    list_filter = ["provider", "model"]
    readonly_fields = ["created_at"]


# ── Publication ───────────────────────────────────────────────────────────────

@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ["article", "target_site", "status", "wp_post_id", "published_at"]
    list_filter = ["status", "target_site"]
    readonly_fields = ["published_at"]
    actions = ["action_promote_to_publish"]

    @admin.action(description="Опубликовать на сайте (снять с черновика)")
    def action_promote_to_publish(self, request, queryset):
        done = errors = 0
        for pub in queryset.select_related("target_site"):
            if not pub.wp_post_id:
                continue
            try:
                WordPressPublisher.update_status(pub.target_site, pub.wp_post_id, "publish")
                done += 1
            except Exception as exc:
                logger.exception("promote failed for publication %d", pub.pk)
                self.message_user(request, f"#{pub.pk}: ошибка — {exc}", messages.ERROR)
                errors += 1
        if done:
            self.message_user(request, f"Снято с черновика: {done} постов.", messages.SUCCESS)
        if not done and not errors:
            self.message_user(request, "Нет постов с wp_post_id для публикации.", messages.WARNING)
