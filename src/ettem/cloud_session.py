"""ETTEM Cloud auth + session storage.

Login goes through Supabase Auth (email+password → access+refresh JWTs).
Tokens are stored encrypted at .ettem/cloud_session.bin using Fernet, keyed
on a hash of the machine_id so a stolen file can't be replayed on another
device.

Access tokens are auto-refreshed when within REFRESH_BUFFER_SECONDS of expiry.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import time
from typing import Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken

from ettem import cloud_config
from ettem.machine_id import get_machine_id


REFRESH_BUFFER_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 15.0


class CloudAuthError(Exception):
    """Raised when login or refresh fails."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclasses.dataclass
class StoredSession:
    access_token: str
    refresh_token: str
    expires_at: int
    user_id: str
    email: str

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))

    @classmethod
    def from_json(cls, blob: str) -> "StoredSession":
        return cls(**json.loads(blob))

    def needs_refresh(self, now: Optional[int] = None) -> bool:
        return (now or int(time.time())) >= self.expires_at - REFRESH_BUFFER_SECONDS


def _derive_fernet_key() -> bytes:
    """Derive a Fernet key from machine_id + a fixed app salt.

    Same device = same key, so the session file is bound to the hardware.
    """
    salt = b"ettem-cloud-session-v1"
    digest = hashlib.sha256(get_machine_id().encode("utf-8") + salt).digest()
    return base64.urlsafe_b64encode(digest)


class CloudSession:
    """Manages the user's Supabase session (login, persistence, refresh)."""

    def __init__(self, http_client: Optional[httpx.Client] = None) -> None:
        self._http = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
        self._fernet = Fernet(_derive_fernet_key())
        self._cached: Optional[StoredSession] = None

    # ------- public API -------

    def login(self, email: str, password: str) -> StoredSession:
        url = f"{cloud_config.get_supabase_url()}/auth/v1/token?grant_type=password"
        resp = self._http.post(
            url,
            headers={
                "apikey": cloud_config.get_supabase_anon_key(),
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
        if resp.status_code >= 400:
            raise CloudAuthError(self._extract_error_msg(resp), resp.status_code)

        session = self._session_from_response(resp.json())
        self._save(session)
        return session

    def logout(self) -> None:
        path = cloud_config.get_cloud_session_path()
        if path.exists():
            path.unlink()
        self._cached = None

    def is_logged_in(self) -> bool:
        return self._load() is not None

    def get_access_token(self) -> str:
        """Return a non-expired access token, refreshing if necessary.

        Raises CloudAuthError if no session is stored or refresh fails.
        """
        session = self._load()
        if session is None:
            raise CloudAuthError("Not logged in", status_code=None)
        if session.needs_refresh():
            session = self._refresh(session)
        return session.access_token

    def get_email(self) -> Optional[str]:
        session = self._load()
        return session.email if session else None

    # ------- internals -------

    def _refresh(self, session: StoredSession) -> StoredSession:
        url = f"{cloud_config.get_supabase_url()}/auth/v1/token?grant_type=refresh_token"
        resp = self._http.post(
            url,
            headers={
                "apikey": cloud_config.get_supabase_anon_key(),
                "Content-Type": "application/json",
            },
            json={"refresh_token": session.refresh_token},
        )
        if resp.status_code >= 400:
            # Refresh failed → clear so the caller is forced back to login
            self.logout()
            raise CloudAuthError(self._extract_error_msg(resp), resp.status_code)

        refreshed = self._session_from_response(resp.json(), fallback=session)
        self._save(refreshed)
        return refreshed

    def _session_from_response(
        self, body: dict, fallback: Optional[StoredSession] = None
    ) -> StoredSession:
        access = body.get("access_token") or ""
        refresh = body.get("refresh_token") or (fallback.refresh_token if fallback else "")
        expires_in = int(body.get("expires_in") or 3600)
        user = body.get("user") or {}
        return StoredSession(
            access_token=access,
            refresh_token=refresh,
            expires_at=int(time.time()) + expires_in,
            user_id=user.get("id") or (fallback.user_id if fallback else ""),
            email=user.get("email") or (fallback.email if fallback else ""),
        )

    def _save(self, session: StoredSession) -> None:
        path = cloud_config.get_cloud_session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self._fernet.encrypt(session.to_json().encode("utf-8"))
        path.write_bytes(encrypted)
        self._cached = session

    def _load(self) -> Optional[StoredSession]:
        if self._cached is not None:
            return self._cached
        path = cloud_config.get_cloud_session_path()
        if not path.exists():
            return None
        try:
            raw = self._fernet.decrypt(path.read_bytes())
            self._cached = StoredSession.from_json(raw.decode("utf-8"))
            return self._cached
        except (InvalidToken, ValueError, json.JSONDecodeError):
            # File corrupt or bound to a different machine → discard
            path.unlink()
            return None

    @staticmethod
    def _extract_error_msg(resp: httpx.Response) -> str:
        try:
            body = resp.json()
        except Exception:
            return resp.text or f"HTTP {resp.status_code}"
        return (
            body.get("error_description")
            or body.get("msg")
            or body.get("error")
            or body.get("message")
            or f"HTTP {resp.status_code}"
        )
