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
    actions = ["action_check_connection", "action_sync_categories"]

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

    class Media:
        js = ("newsroom/admin/source_admin.js",)

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
