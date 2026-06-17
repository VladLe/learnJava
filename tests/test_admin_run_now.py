from unittest.mock import patch

import pytest

from newsroom.models import Source


@pytest.mark.django_db
def test_run_now_action_invokes_pipeline(admin_client, target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)

    fake_result = {
        "fetched": 3, "skipped": 0, "extracted": 3,
        "rewritten": 3, "published": 3, "failed": 0,
    }
    with patch("newsroom.pipeline.run_source", return_value=fake_result) as mock_run:
        resp = admin_client.post(
            "/admin/newsroom/source/",
            {"action": "action_run_now", "_selected_action": [source.pk]},
        )

    assert resp.status_code in (200, 302)
    mock_run.assert_called_once()


@pytest.mark.django_db
def test_run_now_action_reports_error(admin_client, target_site):
    source = Source.objects.create(name="S", url="https://f.example.com", target_site=target_site)

    with patch("newsroom.pipeline.run_source", side_effect=RuntimeError("boom")):
        resp = admin_client.post(
            "/admin/newsroom/source/",
            {"action": "action_run_now", "_selected_action": [source.pk]},
            follow=True,
        )

    assert resp.status_code == 200
    # source should be untouched / no crash
    source.refresh_from_db()
    assert source.name == "S"
