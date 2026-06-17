from unittest.mock import patch

import pytest

from newsroom.models import Source
from newsroom import pipeline


@pytest.mark.django_db
def test_run_source_calls_all_stages_in_order(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)

    calls = []

    def record(name, ret):
        def _fn(src):
            calls.append(name)
            assert src == source
            return ret
        return _fn

    with (
        patch("newsroom.pipeline.fetch_and_store", side_effect=record("fetch", (2, 1))),
        patch("newsroom.pipeline.extract_articles", side_effect=record("extract", (2, 0))),
        patch("newsroom.pipeline.rewrite_articles", side_effect=record("rewrite", (2, 0))),
        patch("newsroom.pipeline.publish_articles", side_effect=record("publish", (2, 0))),
    ):
        result = pipeline.run_source(source)

    assert calls == ["fetch", "extract", "rewrite", "publish"]
    assert result == {
        "fetched": 2,
        "skipped": 1,
        "extracted": 2,
        "rewritten": 2,
        "published": 2,
        "failed": 0,
    }


@pytest.mark.django_db
def test_run_source_aggregates_failures(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)

    with (
        patch("newsroom.pipeline.fetch_and_store", return_value=(3, 0)),
        patch("newsroom.pipeline.extract_articles", return_value=(2, 1)),
        patch("newsroom.pipeline.rewrite_articles", return_value=(1, 1)),
        patch("newsroom.pipeline.publish_articles", return_value=(1, 0)),
    ):
        result = pipeline.run_source(source)

    assert result["failed"] == 2  # 1 extract + 1 rewrite + 0 publish
