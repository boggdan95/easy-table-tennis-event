"""Tests for the cloud login + tournament listing UI routes."""

from __future__ import annotations

import json
import os
import tempfile
import time
from unittest.mock import MagicMock

import httpx
import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
_tmp_db.close()
os.environ["ETTEM_DB_PATH"] = _tmp_db.name

from fastapi.testclient import TestClient  # noqa: E402

from ettem import cloud_config, cloud_session as cs_module  # noqa: E402
from ettem.cloud_session import CloudAuthError, CloudSession, StoredSession  # noqa: E402
from ettem.cloud_sync import CloudSyncClient, CloudSyncError  # noqa: E402
from ettem.webapp import app as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_session(tmp_path, monkeypatch):
    """Per-test session file + reset module-level singletons."""
    session_file = tmp_path / "cloud_session.bin"
    monkeypatch.setattr(cloud_config, "get_cloud_session_path", lambda: session_file)
    monkeypatch.setattr(cs_module, "get_machine_id", lambda: "test-machine-ui")

    monkeypatch.setattr(app_module, "_cloud_session", None)
    monkeypatch.setattr(app_module, "_cloud_client", None)
    yield session_file


@pytest.fixture
def client():
    return TestClient(app_module.app, follow_redirects=False)


def _seed_logged_in_session(monkeypatch):
    sess = CloudSession()
    sess._save(
        StoredSession(
            access_token="access-1",
            refresh_token="rfsh-1",
            expires_at=int(time.time()) + 3600,
            user_id="u1",
            email="admin@fgtm.test",
        )
    )
    monkeypatch.setattr(app_module, "_cloud_session", sess)
    return sess


def _install_mock_client(monkeypatch, mock_obj):
    monkeypatch.setattr(app_module, "_cloud_client", mock_obj)


def test_cloud_login_page_renders(client):
    resp = client.get("/cloud/login")
    assert resp.status_code == 200
    assert "ETTEM Cloud" in resp.text or "Cloud" in resp.text


def test_login_already_logged_in_redirects(client, monkeypatch):
    _seed_logged_in_session(monkeypatch)
    resp = client.get("/cloud/login")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cloud/tournaments"


def test_login_post_success_redirects(client, monkeypatch):
    mock_sess = MagicMock(spec=CloudSession)
    mock_sess.login.return_value = StoredSession(
        access_token="a", refresh_token="r", expires_at=9999999999,
        user_id="u", email="x@x.test",
    )
    monkeypatch.setattr(app_module, "_cloud_session", mock_sess)

    resp = client.post(
        "/cloud/login",
        data={"email": "admin@fgtm.test", "password": "good"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cloud/tournaments"
    mock_sess.login.assert_called_once_with("admin@fgtm.test", "good")


def test_login_post_bad_credentials_renders_error(client, monkeypatch):
    mock_sess = MagicMock(spec=CloudSession)
    mock_sess.login.side_effect = CloudAuthError("Invalid credentials", status_code=400)
    monkeypatch.setattr(app_module, "_cloud_session", mock_sess)

    resp = client.post(
        "/cloud/login",
        data={"email": "admin@fgtm.test", "password": "bad"},
    )
    assert resp.status_code == 200
    assert "Invalid credentials" in resp.text
    assert "admin@fgtm.test" in resp.text  # email field re-populated


def test_logout_clears_session_and_redirects(client, monkeypatch):
    mock_sess = MagicMock(spec=CloudSession)
    monkeypatch.setattr(app_module, "_cloud_session", mock_sess)

    resp = client.post("/cloud/logout")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cloud/login"
    mock_sess.logout.assert_called_once()


def test_tournaments_page_requires_login(client):
    resp = client.get("/cloud/tournaments")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cloud/login"


def test_tournaments_page_renders_list(client, monkeypatch):
    _seed_logged_in_session(monkeypatch)
    mock_client = MagicMock(spec=CloudSyncClient)
    mock_client.list_tournaments.return_value = [
        {
            "id": "9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a",
            "name": "Open Nacional Guatemala 2026",
            "starts_on": "2026-06-01",
            "ends_on": "2026-06-02",
            "venue": "Polideportivo Zona 13",
            "status": "registration_closed",
            "archived_at": None,
        }
    ]
    _install_mock_client(monkeypatch, mock_client)

    resp = client.get("/cloud/tournaments")
    assert resp.status_code == 200
    assert "Open Nacional Guatemala 2026" in resp.text
    assert "registration_closed" in resp.text
    assert "admin@fgtm.test" in resp.text


def test_tournaments_page_empty_state(client, monkeypatch):
    _seed_logged_in_session(monkeypatch)
    mock_client = MagicMock(spec=CloudSyncClient)
    mock_client.list_tournaments.return_value = []
    _install_mock_client(monkeypatch, mock_client)

    resp = client.get("/cloud/tournaments")
    assert resp.status_code == 200
    # Empty state copy from i18n
    assert "Todavía no hay torneos" in resp.text or "No tournaments" in resp.text


def test_tournaments_page_sync_error_shown(client, monkeypatch):
    _seed_logged_in_session(monkeypatch)
    mock_client = MagicMock(spec=CloudSyncClient)
    mock_client.list_tournaments.side_effect = CloudSyncError(
        "quota_exceeded", error_code="quota_exceeded", status_code=429
    )
    _install_mock_client(monkeypatch, mock_client)

    resp = client.get("/cloud/tournaments")
    assert resp.status_code == 200
    assert "quota_exceeded" in resp.text


def test_tournaments_page_auth_error_bounces_to_login(client, monkeypatch):
    _seed_logged_in_session(monkeypatch)
    mock_client = MagicMock(spec=CloudSyncClient)
    mock_client.list_tournaments.side_effect = CloudAuthError("session gone")
    _install_mock_client(monkeypatch, mock_client)

    resp = client.get("/cloud/tournaments")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/cloud/login"


# ---------------------------------------------------------------------------
# list_tournaments on the client itself (PostgREST direct call)
# ---------------------------------------------------------------------------


def test_list_tournaments_hits_postgrest_directly(monkeypatch, tmp_path):
    """End-to-end test of CloudSyncClient.list_tournaments with a mocked HTTP transport."""
    monkeypatch.setattr(cloud_config, "get_cloud_session_path", lambda: tmp_path / "s.bin")
    monkeypatch.setattr(cs_module, "get_machine_id", lambda: "test-machine-list")
    monkeypatch.setenv("ETTEM_CLOUD_URL", "https://test.supabase.co")
    monkeypatch.setenv("ETTEM_CLOUD_ANON_KEY", "anon-test")

    def handler(request):
        assert request.url.path == "/rest/v1/tournaments"
        assert request.headers["authorization"] == "Bearer access-1"
        assert "archived_at" in request.url.params
        return httpx.Response(
            200,
            json=[
                {"id": "uuid-1", "name": "T1", "status": "draft",
                 "starts_on": None, "ends_on": None, "venue": None, "archived_at": None}
            ],
        )

    session = CloudSession()
    session._save(StoredSession(
        access_token="access-1", refresh_token="r",
        expires_at=int(time.time()) + 3600,
        user_id="u", email="x@x.test",
    ))
    client = CloudSyncClient(
        session,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = client.list_tournaments()
    assert len(result) == 1
    assert result[0]["name"] == "T1"
