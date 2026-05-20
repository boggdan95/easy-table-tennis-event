"""ETTEM Cloud configuration: URL, anon key, device identity.

URL and anon key are baked at build time from environment variables so
PyInstaller produces a binary pre-pointed at the right Supabase project.
Both override at runtime via env vars for dev.

Device ID is derived deterministically from machine_id so the same physical
device acquires the same lock across reinstalls — see contracts/api-v1.json
for the device_id format constraints.
"""

from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path

from ettem.machine_id import get_machine_id
from ettem.paths import get_data_dir


DEFAULT_SUPABASE_URL = "https://kkfidgtmpbxfmzyiwwaa.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = ""


def get_supabase_url() -> str:
    return os.environ.get("ETTEM_CLOUD_URL", DEFAULT_SUPABASE_URL).rstrip("/")


def get_supabase_anon_key() -> str:
    return os.environ.get("ETTEM_CLOUD_ANON_KEY", DEFAULT_SUPABASE_ANON_KEY)


def get_device_id() -> str:
    """Stable per-device identifier shaped to the contract's device_id pattern.

    Format: ettem-{os}-{16hex} where 16hex is a SHA-256 of the machine_id.
    Length is 26-27 chars, well within the 8-128 range, only [A-Za-z0-9.-] used.
    """
    machine_hash = hashlib.sha256(get_machine_id().encode("utf-8")).hexdigest()[:16]
    os_slug = {"Darwin": "mac", "Windows": "win", "Linux": "linux"}.get(
        platform.system(), "x"
    )
    return f"ettem-{os_slug}-{machine_hash}"


def get_cloud_session_path() -> Path:
    return get_data_dir() / "cloud_session.bin"


def get_device_id_path() -> Path:
    return get_data_dir() / "device_id"
