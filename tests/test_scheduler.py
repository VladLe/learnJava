from unittest.mock import MagicMock, patch

import pytest

from newsroom.models import Source
from newsroom import scheduler


@pytest.mark.django_db
def test_run_source_job_runs_enabled_source(target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)

    with patch("newsroom.pipeline.run_source") as mock_run:
        scheduler.run_source_job(source.id)

    mock_run.assert_called_once()
    assert mock_run.call_args[0][0].id == source.id


@pytest.mark.django_db
def test_run_source_job_skips_disabled_source(target_site):
    source = Source.objects.create(
        name="S", url="https://f.example.com", target_site=target_site, enabled=False
    )

    with patch("newsroom.pipeline.run_source") as mock_run:
        scheduler.run_source_job(source.id)

    mock_run.assert_not_called()


@pytest.mark.django_db
def test_run_source_job_skips_missing_source():
    with patch("newsroom.pipeline.run_source") as mock_run:
        scheduler.run_source_job(999999)

    mock_run.assert_not_called()


@pytest.mark.django_db
def test_register_jobs_adds_one_job_per_enabled_source(target_site):
    s1 = Source.objects.create(
        name="S1", url="https://f1.example.com", target_site=target_site,
        fetch_interval_minutes=30,
    )
    Source.objects.create(
        name="S2", url="https://f2.example.com", target_site=target_site, enabled=False
    )

    mock_scheduler = MagicMock()
    scheduler.register_jobs(mock_scheduler)

    assert mock_scheduler.add_job.call_count == 1
    _, kwargs = mock_scheduler.add_job.call_args
    assert kwargs["id"] == f"source-{s1.id}"
    assert kwargs["args"] == [s1.id]
