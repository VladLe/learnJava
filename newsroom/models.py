from django.db import models
from encrypted_model_fields.fields import EncryptedCharField


class TargetSite(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISH = "publish", "Publish"

    name = models.CharField(max_length=255)
    base_url = models.URLField()
    auth_user = models.CharField(max_length=255)
    auth_app_password = EncryptedCharField(max_length=500)
    default_status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Target site"
        verbose_name_plural = "Target sites"

    def __str__(self):
        return self.name


class WordPressCategory(models.Model):
    site = models.ForeignKey(TargetSite, on_delete=models.CASCADE, related_name="categories")
    wp_category_id = models.IntegerField()
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WordPress category"
        verbose_name_plural = "WordPress categories"
        unique_together = [("site", "wp_category_id")]

    def __str__(self):
        return f"{self.site.name} / {self.name}"


class Source(models.Model):
    class SourceType(models.TextChoices):
        RSS = "rss", "RSS"

    class Tone(models.TextChoices):
        NEUTRAL = "neutral", "Neutral"
        ANALYTICAL = "analytical", "Analytical"
        CONVERSATIONAL = "conversational", "Conversational"

    class TargetLength(models.TextChoices):
        SHORT = "short", "Short"
        MEDIUM = "medium", "Medium"
        LONG = "long", "Long"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.RSS)
    url = models.URLField()
    enabled = models.BooleanField(default=True)
    fetch_interval_minutes = models.IntegerField(default=60)
    target_site = models.ForeignKey(TargetSite, on_delete=models.CASCADE, related_name="sources")
    target_category = models.ForeignKey(
        WordPressCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="sources"
    )
    post_status = models.CharField(max_length=10, blank=True, default="")
    tone = models.CharField(max_length=20, choices=Tone.choices, default=Tone.NEUTRAL)
    target_length = models.CharField(
        max_length=10, choices=TargetLength.choices, default=TargetLength.MEDIUM
    )
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Source"
        verbose_name_plural = "Sources"

    def __str__(self):
        return self.name


class Article(models.Model):
    class Status(models.TextChoices):
        FETCHED = "fetched", "Fetched"
        EXTRACTED = "extracted", "Extracted"
        REWRITTEN = "rewritten", "Rewritten"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="articles")
    guid = models.CharField(max_length=512)
    source_url = models.URLField(max_length=2048)
    url_hash = models.CharField(max_length=64, unique=True)
    original_title = models.CharField(max_length=1024)
    original_summary = models.TextField(blank=True, default="")
    full_text = models.TextField(blank=True, default="")
    published_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.FETCHED)
    error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["source", "published_at"]),
        ]

    def __str__(self):
        return self.original_title


class RewrittenContent(models.Model):
    article = models.OneToOneField(Article, on_delete=models.CASCADE, related_name="rewritten")
    title = models.CharField(max_length=1024)
    body_html = models.TextField()
    excerpt = models.TextField()
    seo_title = models.CharField(max_length=1024)
    seo_description = models.TextField()
    tags = models.JSONField(default=list)
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=100)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rewritten content"
        verbose_name_plural = "Rewritten content"

    def __str__(self):
        return f"Rewrite of: {self.article}"


class Publication(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="publications")
    target_site = models.ForeignKey(TargetSite, on_delete=models.CASCADE, related_name="publications")
    wp_post_id = models.IntegerField(null=True, blank=True)
    wp_url = models.URLField(max_length=2048, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices)
    error = models.TextField(blank=True, default="")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Publication"
        verbose_name_plural = "Publications"
        unique_together = [("article", "target_site")]

    def __str__(self):
        return f"{self.article} → {self.target_site}"
