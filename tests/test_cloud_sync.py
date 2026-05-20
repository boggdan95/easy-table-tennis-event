"""Tests for the cloud sync client (login, session, RPCs)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
import pytest

from ettem import cloud_config, cloud_session, cloud_sync
from ettem.cloud_session import CloudAuthError, CloudSession, StoredSession
from ettem.cloud_sync import CloudSyncClient, CloudSyncError


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_session_path(tmp_path, monkeypatch):
    """Redirect cloud_session.bin to a temp file so tests don't touch the real .ettem/."""
    session_file = tmp_path / "cloud_session.bin"
    monkeypatch.setattr(
        cloud_config, "get_cloud_session_path", lambda: session_file
    )
    return session_file


@pytest.fixture(autouse=True)
def fixed_machine_id(monkeypatch):
    """Pin machine_id so Fernet key is stable across tests."""
    monkeypatch.setattr(
        cloud_session, "get_machine_id", lambda: "test-machine-id-abc123"
    )
    monkeypatch.setattr(
        "ettem.cloud_config.get_machine_id", lambda: "test-machine-id-abc123"
    )


@pytest.fixture(autouse=True)
def cloud_creds(monkeypatch):
    monkeypatch.setenv("ETTEM_CLOUD_URL", "https://test.supabase.co")
    monkeypatch.setenv("ETTEM_CLOUD_ANON_KEY", "anon-key-test")


def make_mock_client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


# ---------------------------------------------------------------------------
# cloud_config
# ---------------------------------------------------------------------------


def test_device_id_format_matches_contract():
    device_id = cloud_config.get_device_id()
    assert 8 <= len(device_id) <= 128
    assert re.match(r"^[A-Za-z0-9._:-]+$", device_id)


def test_device_id_is_deterministic():
    a = cloud_config.get_device_id()
    b = cloud_config.get_device_id()
    assert a == b


# ---------------------------------------------------------------------------
# CloudSession: login + storage
# ---------------------------------------------------------------------------


def test_login_persists_encrypted_session(isolated_session_path):
    def handler(request):
        assert request.url.path == "/auth/v1/token"
        assert request.url.params.get("grant_type") == "password"
        return httpx.Response(
            200,
            json={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
                "user": {"id": "user-uuid", "email": "test@fgtm.test"},
            },
        )

    session = CloudSession(http_client=make_mock_client(handler))
    stored = session.login("test@fgtm.test", "secret")

    assert stored.access_token == "access-1"
    assert stored.refresh_token == "refresh-1"
    assert stored.email == "test@fgtm.test"
    assert isolated_session_path.exists()

    # File must be encrypted (not contain raw token)
    blob = isolated_session_path.read_bytes()
    assert b"access-1" not in blob


def test_login_failure_raises_with_status(isolated_session_path):
    def handler(request):
        return httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "Invalid credentials"}
        )

    session = CloudSession(http_client=make_mock_client(handler))
    with pytest.raises(CloudAuthError) as exc_info:
        session.login("test@fgtm.test", "wrong")
    assert exc_info.value.status_code == 400
    assert "Invalid credentials" in str(exc_info.value)
    assert not isolated_session_path.exists()


def test_logout_removes_session_file(isolated_session_path):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "access_token": "a",
                "refresh_token": "r",
                "expires_in": 3600,
                "user": {"id": "u", "email": "e@e.test"},
            },
        )

    session = CloudSession(http_client=make_mock_client(handler))
    session.login("e@e.test", "p")
    assert isolated_session_path.exists()

    session.logout()
    assert not isolated_session_path.exists()
    assert not session.is_logged_in()


def test_corrupt_session_file_is_discarded(isolated_session_path):
    isolated_session_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_session_path.write_bytes(b"not-a-valid-fernet-blob")

    session = CloudSession()
    assert session.is_logged_in() is False
    # Side effect: corrupt file should be cleaned up
    assert not isolated_session_path.exists()


def test_session_round_trip_across_instances(isolated_session_path):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "access_token": "tok-xyz",
                "refresh_token": "rfsh-xyz",
                "expires_in": 3600,
                "user": {"id": "u1", "email": "u1@test.com"},
            },
        )

    CloudSession(http_client=make_mock_client(handler)).login("u1@test.com", "p")

    # New instance loads the persisted session
    fresh = CloudSession()
    assert fresh.is_logged_in()
    assert fresh.get_email() == "u1@test.com"


# ---------------------------------------------------------------------------
# CloudSession: refresh
# ---------------------------------------------------------------------------


def _seed_expired_session(monkeypatch, refresh_token="rfsh-orig"):
    """Drop an expired session file straight into storage."""
    stored = StoredSession(
        access_token="old-access",
        refresh_token=refresh_token,
        expires_at=int(time.time()) - 10,  # already expired
        user_id="u1",
        email="u1@test.com",
    )
    sess = CloudSession()
    sess._save(stored)
    sess._cached = None  # force reload from disk
    return sess


def test_get_access_token_refreshes_when_expired(isolated_session_path, monkeypatch):
    refresh_calls = {"count": 0}

    def handler(request):
        refresh_calls["count"] += 1
        assert request.url.params.get("grant_type") == "refresh_token"
        body = json.loads(request.content.decode("utf-8"))
        assert body["refresh_token"] == "rfsh-orig"
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "rfsh-new",
                "expires_in": 3600,
                "user": {"id": "u1", "email": "u1@test.com"},
            },
        )

    _seed_expired_session(monkeypatch)
    session = CloudSession(http_client=make_mock_client(handler))
    token = session.get_access_token()

    assert token == "new-access"
    assert refresh_calls["count"] == 1


def test_get_access_token_raises_when_not_logged_in():
    session = CloudSession()
    with pytest.raises(CloudAuthError):
        session.get_access_token()


def test_refresh_failure_logs_user_out(isolated_session_path, monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"error": "invalid_grant"})

    _seed_expired_session(monkeypatch)
    session = CloudSession(http_client=make_mock_client(handler))

    with pytest.raises(CloudAuthError):
        session.get_access_token()
    # Session file wiped after failed refresh
    assert not isolated_session_path.exists()


# ---------------------------------------------------------------------------
# CloudSyncClient: pull
# ---------------------------------------------------------------------------


VALID_PULL_RESPONSE = {
    "ok": True,
    "lock": {
        "device_id": "ettem-mac-0000000000000001",
        "acquired_at": "2026-05-20T12:00:00Z",
    },
    "payload": {
        "schema_version": "1.0",
        "generated_at": "2026-05-20T12:00:00Z",
        "tenant": {
            "id": "11111111-1111-1111-1111-111111111111",
            "slug": "fgtm",
            "name": "FGTM",
            "country_cd": "GTM",
            "organizer_name": "FGTM",
            "logo_url": None,
            "primary_color": "#0a5275",
        },
        "tournament": {
            "id": "9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a",
            "name": "Open",
            "starts_on": "2026-06-01",
            "ends_on": "2026-06-02",
            "venue": None,
            "status": "locked_for_run",
            "locked_by_device_id": "ettem-mac-0000000000000001",
            "locked_at": "2026-05-20T12:00:00Z",
        },
        "categories": [
            {
                "id": "aaaa1111-aaaa-1111-aaaa-111111111111",
                "code": "U15BS",
                "name": "Under 15 Boys Singles",
                "age_band": 15,
                "gender": "M",
                "is_global": True,
            }
        ],
        "events": [
            {
                "id": "eeee1111-eeee-1111-eeee-111111111111",
                "category_id": "aaaa1111-aaaa-1111-aaaa-111111111111",
                "event_type": "singles",
                "team_system": None,
                "format": "bo5",
                "status": "open",
            }
        ],
        "players": [],
        "pairs": [],
        "teams": [],
        "registrations": [],
    },
}


def _logged_in_session(isolated_session_path, monkeypatch):
    """Persist a non-expired session so the client can read its token."""
    stored = StoredSession(
        access_token="access-valid",
        refresh_token="rfsh",
        expires_at=int(time.time()) + 3600,
        user_id="u1",
        email="u1@test.com",
    )
    s = CloudSession()
    s._save(stored)
    return s


def test_pull_tournament_validates_and_returns_payload(
    isolated_session_path, monkeypatch
):
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/pull_tournament"
        assert request.headers["authorization"] == "Bearer access-valid"
        params = json.loads(request.content.decode("utf-8"))
        assert params["p_tournament_id"] == "9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a"
        assert params["p_device_id"] == "ettem-mac-0000000000000001"
        assert params["p_schema_version"] == "1.0"
        return httpx.Response(200, json=VALID_PULL_RESPONSE)

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(
        session,
        http_client=make_mock_client(handler),
        device_id="ettem-mac-0000000000000001",
    )
    result = client.pull_tournament("9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a")
    assert result["ok"] is True
    assert result["payload"]["tournament"]["name"] == "Open"


def test_pull_tournament_parses_error_code(isolated_session_path, monkeypatch):
    def handler(request):
        return httpx.Response(
            400,
            json={
                "code": "P0001",
                "message": "tournament_locked_by_other_device",
                "details": json.dumps(
                    {
                        "error_code": "tournament_locked_by_other_device",
                        "locked_by_device_id": "ettem-mac-other",
                        "locked_at": "2026-05-20T11:00:00Z",
                    }
                ),
            },
        )

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(session, http_client=make_mock_client(handler))

    with pytest.raises(CloudSyncError) as exc_info:
        client.pull_tournament("9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a")
    assert exc_info.value.error_code == "tournament_locked_by_other_device"
    assert exc_info.value.details["locked_by_device_id"] == "ettem-mac-other"


def test_pull_tournament_rejects_malformed_payload(
    isolated_session_path, monkeypatch
):
    def handler(request):
        # Missing required fields → schema violation
        return httpx.Response(200, json={"ok": True})

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(session, http_client=make_mock_client(handler))
    with pytest.raises(CloudSyncError) as exc_info:
        client.pull_tournament("9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a")
    assert exc_info.value.error_code == "schema_violation_in_response"


# ---------------------------------------------------------------------------
# CloudSyncClient: push
# ---------------------------------------------------------------------------


VALID_EVENT_BLOCK = {
    "event_id": "eeee1111-eeee-1111-eeee-111111111111",
    "results": [
        {
            "event_id": "eeee1111-eeee-1111-eeee-111111111111",
            "placement": 1,
            "player_id": "dada1111-dada-1111-dada-111111111111",
            "pair_id": None,
            "team_id": None,
            "points_awarded": 100,
        }
    ],
    "audit_blob": {"format": "ettem-desktop-v2.8", "groups": []},
}

VALID_PUSH_RESPONSE = {
    "ok": True,
    "events_closed": ["eeee1111-eeee-1111-eeee-111111111111"],
    "tournament_closed": True,
    "lock_released": True,
}


def test_push_results_success(isolated_session_path, monkeypatch):
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/push_results"
        params = json.loads(request.content.decode("utf-8"))
        assert params["p_close_tournament"] is True
        assert len(params["p_events"]) == 1
        return httpx.Response(200, json=VALID_PUSH_RESPONSE)

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(session, http_client=make_mock_client(handler))
    result = client.push_results(
        "9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a",
        [VALID_EVENT_BLOCK],
        close_tournament=True,
    )
    assert result["tournament_closed"] is True


def test_push_results_rejects_invalid_request_before_http(
    isolated_session_path, monkeypatch
):
    http_called = {"count": 0}

    def handler(request):
        http_called["count"] += 1
        return httpx.Response(200, json=VALID_PUSH_RESPONSE)

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(session, http_client=make_mock_client(handler))

    # Empty events array violates the schema (minItems: 1)
    with pytest.raises(CloudSyncError) as exc_info:
        client.push_results("9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a", [])
    assert exc_info.value.error_code == "schema_violation_in_request"
    assert http_called["count"] == 0  # never hit the wire


def test_push_results_parses_missing_results_error(
    isolated_session_path, monkeypatch
):
    def handler(request):
        return httpx.Response(
            400,
            json={
                "code": "P0001",
                "message": "missing_results_for_registrations",
                "details": json.dumps(
                    {
                        "error_code": "missing_results_for_registrations",
                        "event_id": "eeee1111-eeee-1111-eeee-111111111111",
                        "results_count": 1,
                        "confirmed_count": 4,
                    }
                ),
            },
        )

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(session, http_client=make_mock_client(handler))
    with pytest.raises(CloudSyncError) as exc_info:
        client.push_results(
            "9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a", [VALID_EVENT_BLOCK]
        )
    assert exc_info.value.error_code == "missing_results_for_registrations"
    assert exc_info.value.details["confirmed_count"] == 4


def test_rpc_network_error_wraps_as_cloud_sync_error(
    isolated_session_path, monkeypatch
):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    session = _logged_in_session(isolated_session_path, monkeypatch)
    client = CloudSyncClient(session, http_client=make_mock_client(handler))
    with pytest.raises(CloudSyncError) as exc_info:
        client.pull_tournament("9b3e1f64-0a4d-4d2a-9e2f-5a6c1d7e9b0a")
    assert "Network error" in str(exc_info.value)
    assert exc_info.value.error_code is None
