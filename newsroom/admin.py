from django.contrib import admin

from .models import Article, Publication, RewrittenContent, Source, TargetSite, WordPressCategory


@admin.register(TargetSite)
class TargetSiteAdmin(admin.ModelAdmin):
    list_display = ["name", "base_url", "default_status", "enabled", "created_at"]
    list_filter = ["enabled", "default_status"]
    search_fields = ["name", "base_url"]


@admin.register(WordPressCategory)
class WordPressCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "site", "wp_category_id", "synced_at"]
    list_filter = ["site"]
    search_fields = ["name", "slug"]


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ["name", "url", "target_site", "target_category", "enabled", "last_fetched_at"]
    list_filter = ["enabled", "target_site", "tone", "target_length"]
    search_fields = ["name", "url"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["original_title", "source", "status", "published_at", "fetched_at"]
    list_filter = ["status", "source"]
    search_fields = ["original_title", "source_url"]
    readonly_fields = ["url_hash", "fetched_at"]


@admin.register(RewrittenContent)
class RewrittenContentAdmin(admin.ModelAdmin):
    list_display = ["article", "provider", "model", "input_tokens", "output_tokens", "created_at"]
    list_filter = ["provider", "model"]
    readonly_fields = ["created_at"]


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ["article", "target_site", "status", "wp_post_id", "published_at"]
    list_filter = ["status", "target_site"]
    readonly_fields = ["published_at"]
