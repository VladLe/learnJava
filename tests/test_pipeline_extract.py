from unittest.mock import patch

import pytest

from newsroom.extract.article import ExtractionError
from newsroom.models import Article, Source
from newsroom import pipeline


def _create_fetched_article(source, n=1):
    return Article.objects.create(
        source=source,
        guid=f"guid-{n}",
        source_url=f"https://example.com/article-{n}",
        url_hash=f"hash{n:064d}",
        original_title=f"Article {n}",
        status=Article.Status.FETCHED,
    )


@pytest.mark.django_db
def test_extract_articles_transitions_to_extracted(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _create_fetched_article(source)

    with patch("newsroom.pipeline.extract_text", return_value="Full article text."):
        extracted, failed = pipeline.extract_articles(source)

    assert extracted == 1
    assert failed == 0
    article.refresh_from_db()
    assert article.status == Article.Status.EXTRACTED
    assert article.full_text == "Full article text."
    assert article.error == ""


@pytest.mark.django_db
def test_extract_articles_transitions_to_failed_on_error(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    article = _create_fetched_article(source)

    with patch("newsroom.pipeline.extract_text", side_effect=ExtractionError("timeout")):
        extracted, failed = pipeline.extract_articles(source)

    assert extracted == 0
    assert failed == 1
    article.refresh_from_db()
    assert article.status == Article.Status.FAILED
    assert "timeout" in article.error


@pytest.mark.django_db
def test_extract_articles_continues_after_one_failure(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    a1 = _create_fetched_article(source, 1)
    a2 = _create_fetched_article(source, 2)

    def side_effect(url):
        if "article-1" in url:
            raise ExtractionError("404")
        return "Good text."

    with patch("newsroom.pipeline.extract_text", side_effect=side_effect):
        extracted, failed = pipeline.extract_articles(source)

    assert extracted == 1
    assert failed == 1
    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.status == Article.Status.FAILED
    assert a2.status == Article.Status.EXTRACTED


@pytest.mark.django_db
def test_extract_articles_scoped_to_source(target_site):
    s1 = Source.objects.create(name="S1", url="https://f1.example.com", target_site=target_site)
    s2 = Source.objects.create(name="S2", url="https://f2.example.com", target_site=target_site)
    a1 = _create_fetched_article(s1, 1)
    a2 = _create_fetched_article(s2, 2)

    with patch("newsroom.pipeline.extract_text", return_value="text"):
        pipeline.extract_articles(s1)  # only source 1

    a1.refresh_from_db()
    a2.refresh_from_db()
    assert a1.status == Article.Status.EXTRACTED
    assert a2.status == Article.Status.FETCHED  # untouched


@pytest.mark.django_db
def test_extract_articles_skips_non_fetched(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)
    Article.objects.create(
        source=source, guid="g1", source_url="https://example.com/done",
        url_hash="a" * 64, original_title="Done",
        status=Article.Status.EXTRACTED,
    )

    with patch("newsroom.pipeline.extract_text", return_value="text") as mock_extract:
        extracted, failed = pipeline.extract_articles(source)

    mock_extract.assert_not_called()
    assert extracted == 0
    assert failed == 0
