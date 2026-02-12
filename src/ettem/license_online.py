"""
Online license validation for ETTEM.

Communicates with the license server at ettem.boggdan.com to:
- Activate a license on this machine
- Periodically validate (every 30 days)
- Deactivate (free a machine slot)

Falls back gracefully to offline mode if the server is unreachable.
"""

import json
import ssl
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass, asdict, field

from .paths import get_data_dir
from .machine_id import get_machine_id, get_machine_label

# Server configuration
LICENSE_SERVER_URL = "https://ettem.boggdan.com/api"
API_KEY = "yBAEwIwtof3h6LyWPa9rvXzrV7TsxWUzKng9cmcr6Tw"  # Must match server config.php

# Metadata file
LICENSE_META_FILE = "license.meta"

# Validation intervals
VALIDATION_INTERVAL_DAYS = 30
GRACE_PERIOD_DAYS = 30  # Additional days after interval before blocking

APP_VERSION = "2.3.0"


@dataclass
class LicenseMetadata:
    """Stored metadata about online license validation."""
    machine_id: str
    last_validated_online: Optional[str] = None  # ISO datetime
    last_validation_result: Optional[str] = None  # "ok" or error code
    server_expiration_date: Optional[str] = None  # YYYY-MM-DD
    activated_online: bool = False
    slot: Optional[int] = None
    max_slots: Optional[int] = None


def get_meta_file_path() -> Path:
    """Get the path to the license metadata file."""
    return get_data_dir() / LICENSE_META_FILE


def load_metadata() -> Optional[LicenseMetadata]:
    """Load license metadata from disk."""
    path = get_meta_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LicenseMetadata(**{k: v for k, v in data.items() if k in LicenseMetadata.__dataclass_fields__})
    except Exception:
        return None


def save_metadata(meta: LicenseMetadata) -> None:
    """Save license metadata to disk."""
    path = get_meta_file_path()
    path.write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")


def _api_request(endpoint: str, payload: dict) -> Tuple[bool, dict]:
    """
    Make an API request to the license server.

    Returns:
        (success, response_dict)
    """
    url = f"{LICENSE_SERVER_URL}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-API-Key", API_KEY)
    req.add_header("User-Agent", f"ETTEM/{APP_VERSION}")

    # Create SSL context (use default certs)
    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return True, body
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            return False, body
        except Exception:
            return False, {"status": "error", "code": "HTTP_ERROR", "message": str(e)}
    except Exception as e:
        return False, {"status": "error", "code": "NETWORK_ERROR", "message": str(e)}


def activate_online(license_key: str) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    Try to activate the license online (register this machine).

    Returns:
        (success, error_message, extra_data)
        extra_data may contain 'machines' list when MACHINE_LIMIT error
    """
    machine_id = get_machine_id()
    machine_label = get_machine_label()

    ok, resp = _api_request("activate", {
        "license_key": license_key,
        "machine_id": machine_id,
        "machine_label": machine_label,
        "app_version": APP_VERSION,
    })

    if ok and resp.get("status") == "ok":
        meta = LicenseMetadata(
            machine_id=machine_id,
            last_validated_online=datetime.utcnow().isoformat(),
            last_validation_result="ok",
            server_expiration_date=resp.get("license", {}).get("expiration_date"),
            activated_online=True,
            slot=resp.get("machine", {}).get("slot"),
            max_slots=resp.get("machine", {}).get("max_slots"),
        )
        save_metadata(meta)
        return True, None, None
    else:
        error_msg = resp.get("message", "Online activation failed")
        extra = {}
        if resp.get("code") == "MACHINE_LIMIT":
            extra["machines"] = resp.get("machines", [])
        return False, error_msg, extra or None


def validate_online(license_key: str) -> Tuple[bool, Optional[str]]:
    """
    Periodic online validation.

    Returns:
        (success, error_message)
    """
    meta = load_metadata()
    machine_id = meta.machine_id if meta else get_machine_id()

    ok, resp = _api_request("validate", {
        "license_key": license_key,
        "machine_id": machine_id,
        "app_version": APP_VERSION,
    })

    if ok and resp.get("status") == "ok":
        if not meta:
            meta = LicenseMetadata(machine_id=machine_id)
        meta.last_validated_online = datetime.utcnow().isoformat()
        meta.last_validation_result = "ok"
        meta.server_expiration_date = resp.get("license", {}).get("expiration_date")
        meta.slot = resp.get("machine", {}).get("slot")
        meta.max_slots = resp.get("machine", {}).get("max_slots")
        save_metadata(meta)
        return True, None
    else:
        error_code = resp.get("code", "UNKNOWN")
        error_msg = resp.get("message", "Validation failed")
        if meta and error_code in ("REVOKED", "MACHINE_NOT_FOUND"):
            meta.last_validation_result = error_code
            save_metadata(meta)
        return False, error_msg


def deactivate_online(license_key: str) -> Tuple[bool, Optional[str]]:
    """
    Deactivate this machine from the license (free a slot).

    Returns:
        (success, error_message)
    """
    meta = load_metadata()
    machine_id = meta.machine_id if meta else get_machine_id()

    ok, resp = _api_request("deactivate", {
        "license_key": license_key,
        "machine_id": machine_id,
    })

    # Remove local metadata regardless of server response
    path = get_meta_file_path()
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

    if ok:
        return True, None
    return False, resp.get("message", "Deactivation failed")


def needs_online_validation() -> bool:
    """Check if we need to perform an online validation (>30 days since last)."""
    meta = load_metadata()
    if not meta or not meta.last_validated_online:
        return True

    try:
        last = datetime.fromisoformat(meta.last_validated_online)
        days_since = (datetime.utcnow() - last).days
        return days_since >= VALIDATION_INTERVAL_DAYS
    except Exception:
        return True


def is_within_grace_period() -> bool:
    """
    Check if still within the offline grace period.

    Returns True if:
    - Never activated online (pure offline mode, backwards compat)
    - Within 60 days of last successful validation
    Returns False if:
    - Activated online AND last validation was >60 days ago
    - Last validation result was a hard revocation
    """
    meta = load_metadata()

    # Never activated online = pure offline license = always allowed
    if not meta or not meta.activated_online:
        return True

    # Hard revocation from server
    if meta.last_validation_result in ("REVOKED", "MACHINE_NOT_FOUND"):
        return False

    if not meta.last_validated_online:
        return True  # Activated but never validated = still in first period

    try:
        last = datetime.fromisoformat(meta.last_validated_online)
        days_since = (datetime.utcnow() - last).days
        return days_since < (VALIDATION_INTERVAL_DAYS + GRACE_PERIOD_DAYS)
    except Exception:
        return True  # On parse error, be permissive
