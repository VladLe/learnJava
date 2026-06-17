from django.db.models import Count, Sum

from .models import Article, Publication, RewrittenContent, Source, TargetSite


def compute_metrics() -> dict:
    """Aggregate pipeline metrics for the admin dashboard."""
    status_counts = dict(
        Article.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )
    article_statuses = [
        {"status": value, "label": label, "count": status_counts.get(value, 0)}
        for value, label in Article.Status.choices
    ]

    pub_counts = dict(
        Publication.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )

    token_totals = RewrittenContent.objects.aggregate(
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        rewrites=Count("id"),
    )

    by_model = list(
        RewrittenContent.objects.values("provider", "model")
        .annotate(
            rewrites=Count("id"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
        )
        .order_by("-rewrites")
    )

    return {
        "articles_total": Article.objects.count(),
        "article_statuses": article_statuses,
        "publications_published": pub_counts.get(Publication.Status.PUBLISHED, 0),
        "publications_failed": pub_counts.get(Publication.Status.FAILED, 0),
        "tokens_input": token_totals["input_tokens"] or 0,
        "tokens_output": token_totals["output_tokens"] or 0,
        "rewrites_total": token_totals["rewrites"] or 0,
        "by_model": by_model,
        "sources_total": Source.objects.count(),
        "sources_enabled": Source.objects.filter(enabled=True).count(),
        "sites_total": TargetSite.objects.count(),
        "sites_enabled": TargetSite.objects.filter(enabled=True).count(),
    }
