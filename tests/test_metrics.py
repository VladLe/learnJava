import pytest

from newsroom.metrics import compute_metrics
from newsroom.models import Article, Publication, RewrittenContent, Source


def _article(source, n, status):
    return Article.objects.create(
        source=source, guid=f"g{n}", source_url=f"https://example.com/{n}",
        url_hash=f"h{n:064d}", original_title=f"A{n}", status=status,
    )


@pytest.mark.django_db
def test_compute_metrics_counts_articles_by_status(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    _article(source, 1, Article.Status.FETCHED)
    _article(source, 2, Article.Status.PUBLISHED)
    _article(source, 3, Article.Status.PUBLISHED)

    m = compute_metrics()
    assert m["articles_total"] == 3
    by_status = {row["status"]: row["count"] for row in m["article_statuses"]}
    assert by_status["fetched"] == 1
    assert by_status["published"] == 2
    assert by_status["failed"] == 0


@pytest.mark.django_db
def test_compute_metrics_token_totals(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    a1 = _article(source, 1, Article.Status.REWRITTEN)
    a2 = _article(source, 2, Article.Status.REWRITTEN)
    for a, inp, out in [(a1, 100, 200), (a2, 50, 75)]:
        RewrittenContent.objects.create(
            article=a, title="T", body_html="<p></p>", excerpt="e",
            seo_title="s", seo_description="d", tags=[],
            provider="anthropic", model="claude-opus-4-8",
            input_tokens=inp, output_tokens=out,
        )

    m = compute_metrics()
    assert m["tokens_input"] == 150
    assert m["tokens_output"] == 275
    assert m["rewrites_total"] == 2
    assert m["by_model"][0]["provider"] == "anthropic"
    assert m["by_model"][0]["rewrites"] == 2


@pytest.mark.django_db
def test_compute_metrics_publication_counts(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    a1 = _article(source, 1, Article.Status.PUBLISHED)
    a2 = _article(source, 2, Article.Status.FAILED)
    Publication.objects.create(article=a1, target_site=target_site, status=Publication.Status.PUBLISHED)
    Publication.objects.create(article=a2, target_site=target_site, status=Publication.Status.FAILED)

    m = compute_metrics()
    assert m["publications_published"] == 1
    assert m["publications_failed"] == 1


@pytest.mark.django_db
def test_compute_metrics_empty_db():
    m = compute_metrics()
    assert m["articles_total"] == 0
    assert m["tokens_input"] == 0
    assert m["by_model"] == []


@pytest.mark.django_db
def test_metrics_view_renders_for_admin(admin_client):
    resp = admin_client.get("/admin/metrics/")
    assert resp.status_code == 200
    assert "Метрики" in resp.content.decode()


@pytest.mark.django_db
def test_metrics_view_requires_login(client):
    resp = client.get("/admin/metrics/")
    assert resp.status_code == 302  # redirect to admin login
