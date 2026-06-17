from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from newsroom.models import Source


@pytest.mark.django_db
def test_doctor_runs_with_no_config(settings):
    settings.IMAGE_PROVIDER = "none"
    settings.ANTHROPIC_API_KEY = ""
    out = StringIO()
    call_command("doctor", stdout=out, stderr=StringIO())
    text = out.getvalue()
    assert "База данных" in text
    assert "RSS-источники" in text  # skipped (no sources) but listed


@pytest.mark.django_db
def test_doctor_reports_llm_key_present(settings):
    settings.REWRITE_PROVIDER = "anthropic"
    settings.ANTHROPIC_API_KEY = "test-key"
    out = StringIO()
    call_command("doctor", stdout=out, stderr=StringIO())
    assert "ключ задан" in out.getvalue()


@pytest.mark.django_db
def test_doctor_checks_rss_when_source_exists(target_site, settings):
    settings.ANTHROPIC_API_KEY = "k"
    Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)

    with patch("newsroom.management.commands.doctor.RssFetcher") as mock_fetcher:
        mock_fetcher.return_value.fetch.return_value = [object(), object()]
        out = StringIO()
        call_command("doctor", stdout=out, stderr=StringIO())

    assert "2 записей" in out.getvalue()
