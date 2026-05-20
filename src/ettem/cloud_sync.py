"""ETTEM Cloud sync client — pull_tournament + push_results.

Calls the Supabase RPCs via PostgREST. Validates outgoing requests and
incoming responses against the bundled api-v1.json contract.

Errors from the RPC come back as PostgREST error envelopes with a JSON
DETAIL string carrying the contract's error_code; this module re-raises
them as CloudSyncError with .error_code populated so callers can branch
on stable codes instead of HTTP statuses or message strings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import httpx
from jsonschema import Draft202012Validator

from ettem import cloud_config
from ettem.cloud_session import CloudSession, DEFAULT_TIMEOUT_SECONDS


SCHEMA_VERSION = "1.0"
_CONTRACT_PATH = Path(__file__).parent / "contracts" / "api-v1.json"


class CloudSyncError(Exception):
    """Raised on contract violations or RPC error responses.

    .error_code is the stable identifier from api-v1.json's error catalog
    (e.g. "tournament_locked_by_other_device"). May be None for transport-
    level failures (network, malformed response).
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


def _load_contract() -> dict:
    with _CONTRACT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


_CONTRACT = _load_contract()


def _validator_for(def_key: str) -> Draft202012Validator:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{def_key}",
        "$defs": _CONTRACT["$defs"],
    }
    return Draft202012Validator(schema)


_VALIDATORS = {
    "pull_response":  _validator_for("pull_tournament_response_ok"),
    "push_request":   _validator_for("push_results_request"),
    "push_response":  _validator_for("push_results_response_ok"),
}


class CloudSyncClient:
    """High-level client for the ETTEM Cloud RPCs."""

    def __init__(
        self,
        session: CloudSession,
        *,
        http_client: Optional[httpx.Client] = None,
        device_id: Optional[str] = None,
    ) -> None:
        self._session = session
        self._http = http_client or httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS)
        self._device_id = device_id or cloud_config.get_device_id()

    @property
    def device_id(self) -> str:
        return self._device_id

    def pull_tournament(
        self, tournament_id: str, *, force_acquire: bool = False
    ) -> dict:
        """Acquire lock + snapshot tournament. Returns the validated payload dict."""
        body = self._rpc(
            "pull_tournament",
            {
                "p_tournament_id": tournament_id,
                "p_device_id": self._device_id,
                "p_schema_version": SCHEMA_VERSION,
                "p_force_acquire": force_acquire,
            },
        )
        errors = list(_VALIDATORS["pull_response"].iter_errors(body))
        if errors:
            raise CloudSyncError(
                f"Pull response failed schema validation: {errors[0].message}",
                error_code="schema_violation_in_response",
                details={"path": list(errors[0].absolute_path)},
            )
        return body

    def push_results(
        self,
        tournament_id: str,
        events: list[dict],
        *,
        close_tournament: bool = False,
    ) -> dict:
        """Publish event_results blocks. Validates request before sending."""
        request = {
            "schema_version": SCHEMA_VERSION,
            "tournament_id": tournament_id,
            "device_id": self._device_id,
            "events": events,
            "close_tournament": close_tournament,
        }
        errors = list(_VALIDATORS["push_request"].iter_errors(request))
        if errors:
            raise CloudSyncError(
                f"Push request failed schema validation: {errors[0].message}",
                error_code="schema_violation_in_request",
                details={"path": list(errors[0].absolute_path)},
            )

        body = self._rpc(
            "push_results",
            {
                "p_tournament_id": tournament_id,
                "p_device_id": self._device_id,
                "p_events": events,
                "p_schema_version": SCHEMA_VERSION,
                "p_close_tournament": close_tournament,
            },
        )
        errors = list(_VALIDATORS["push_response"].iter_errors(body))
        if errors:
            raise CloudSyncError(
                f"Push response failed schema validation: {errors[0].message}",
                error_code="schema_violation_in_response",
                details={"path": list(errors[0].absolute_path)},
            )
        return body

    # ------- internals -------

    def _rpc(self, name: str, params: dict) -> Any:
        token = self._session.get_access_token()
        url = f"{cloud_config.get_supabase_url()}/rest/v1/rpc/{name}"
        try:
            resp = self._http.post(
                url,
                headers={
                    "apikey": cloud_config.get_supabase_anon_key(),
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=params,
            )
        except httpx.HTTPError as exc:
            raise CloudSyncError(
                f"Network error calling {name}: {exc}", error_code=None
            ) from exc

        if resp.status_code >= 400:
            self._raise_for_error(name, resp)

        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise CloudSyncError(
                f"Malformed response from {name}: not JSON",
                status_code=resp.status_code,
            ) from exc

    @staticmethod
    def _raise_for_error(name: str, resp: httpx.Response) -> None:
        """Map a PostgREST error envelope to CloudSyncError with .error_code.

        Our RPCs raise with SQLSTATE P0001 and a JSON-shaped DETAIL containing
        an error_code field. PostgREST surfaces DETAIL in the response body's
        "details" or "detail" key depending on version.
        """
        try:
            body = resp.json()
        except Exception:
            raise CloudSyncError(
                f"{name} failed with HTTP {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )

        detail_raw = body.get("details") or body.get("detail") or ""
        error_code: Optional[str] = None
        parsed_details: dict = {}

        if isinstance(detail_raw, str) and detail_raw.startswith("{"):
            try:
                parsed_details = json.loads(detail_raw)
                error_code = parsed_details.get("error_code")
            except json.JSONDecodeError:
                pass
        elif isinstance(detail_raw, dict):
            parsed_details = detail_raw
            error_code = detail_raw.get("error_code")

        message = (
            parsed_details.get("message")
            or body.get("message")
            or body.get("hint")
            or detail_raw
            or f"{name} failed"
        )
        raise CloudSyncError(
            message,
            error_code=error_code,
            status_code=resp.status_code,
            details=parsed_details,
        )
