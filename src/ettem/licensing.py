"""
License management for ETTEM.

License format: ETTEM-CCCC-MMYY-SSSSSSSS
- CCCC: Client ID (4 alphanumeric characters)
- MMYY: Expiration month and year
- SSSSSSSS: HMAC signature (8 characters)

Example: ETTEM-JN01-0726-K8M2X9P4
"""

import hmac
import hashlib
import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

from .paths import get_data_dir


# Secret key for HMAC signature - DO NOT SHARE THIS!
# This is embedded in the compiled executable and used to sign licenses.
# If someone gets this key, they can generate their own licenses.
_SECRET_KEY = b"572d0294f72e6afd3dc8b4b8510fdfe01f35ff4810818ee7e1d19cd07bf126cd"

# License file name
LICENSE_FILE = "license.key"


@dataclass
class LicenseInfo:
    """Information about a license."""
    client_id: str
    expiration_date: date
    is_valid: bool
    days_remaining: int
    raw_key: str
    # Online validation fields
    online_status: Optional[str] = None   # "ok", "grace_period", "offline_only", "revoked"
    machine_slot: Optional[str] = None    # "1/2"
    last_online_check: Optional[str] = None  # ISO datetime

    @property
    def is_expired(self) -> bool:
        return self.days_remaining < 0

    @property
    def expiration_str(self) -> str:
        return self.expiration_date.strftime("%m/%Y")


def _generate_signature(client_id: str, month: int, year: int) -> str:
    """
    Generate HMAC signature for license validation.

    Args:
        client_id: 4-character client identifier
        month: Expiration month (1-12)
        year: Expiration year (2-digit, e.g., 26 for 2026)

    Returns:
        8-character signature string
    """
    # Create the data to sign
    data = f"{client_id.upper()}{month:02d}{year:02d}".encode()

    # Generate HMAC-SHA256
    signature = hmac.new(_SECRET_KEY, data, hashlib.sha256).hexdigest()

    # Take first 8 characters and convert to uppercase alphanumeric
    return signature[:8].upper()


def generate_license_key(client_id: str, expiration_month: int, expiration_year: int) -> str:
    """
    Generate a license key for a client.

    Args:
        client_id: 4-character client identifier (e.g., "JN01")
        expiration_month: Month when license expires (1-12)
        expiration_year: Year when license expires (2-digit, e.g., 26 for 2026)

    Returns:
        License key string (e.g., "ETTEM-JN01-0726-K8M2X9P4")

    Raises:
        ValueError: If parameters are invalid
    """
    # Validate client_id
    if not client_id or len(client_id) != 4:
        raise ValueError("Client ID must be exactly 4 characters")
    if not client_id.isalnum():
        raise ValueError("Client ID must be alphanumeric")

    # Validate month
    if not 1 <= expiration_month <= 12:
        raise ValueError("Month must be between 1 and 12")

    # Validate year (2-digit)
    if not 0 <= expiration_year <= 99:
        raise ValueError("Year must be 2 digits (0-99)")

    client_id = client_id.upper()
    signature = _generate_signature(client_id, expiration_month, expiration_year)

    return f"ETTEM-{client_id}-{expiration_month:02d}{expiration_year:02d}-{signature}"


def validate_license_key(key: str) -> Tuple[bool, Optional[LicenseInfo], Optional[str]]:
    """
    Validate a license key.

    Args:
        key: License key to validate

    Returns:
        Tuple of (is_valid, license_info, error_message)
        - is_valid: True if the key is valid and not expired
        - license_info: LicenseInfo object if key format is valid, None otherwise
        - error_message: Error description if invalid, None otherwise
    """
    if not key:
        return False, None, "No se proporcionó clave de licencia"

    # Clean the key
    key = key.strip().upper()

    # Check format: ETTEM-XXXX-MMYY-SSSSSSSS
    parts = key.split("-")
    if len(parts) != 4:
        return False, None, "Formato de clave inválido"

    prefix, client_id, date_part, signature = parts

    # Validate prefix
    if prefix != "ETTEM":
        return False, None, "Prefijo de clave inválido"

    # Validate client_id
    if len(client_id) != 4 or not client_id.isalnum():
        return False, None, "ID de cliente inválido"

    # Validate date part
    if len(date_part) != 4 or not date_part.isdigit():
        return False, None, "Fecha de expiración inválida"

    month = int(date_part[:2])
    year = int(date_part[2:])

    if not 1 <= month <= 12:
        return False, None, "Mes de expiración inválido"

    # Validate signature
    if len(signature) != 8:
        return False, None, "Firma de clave inválida"

    # Verify HMAC signature
    expected_signature = _generate_signature(client_id, month, year)
    if not hmac.compare_digest(signature, expected_signature):
        return False, None, "Clave de licencia no válida"

    # Calculate expiration date (last day of the expiration month)
    full_year = 2000 + year
    if month == 12:
        expiration_date = date(full_year + 1, 1, 1)
    else:
        expiration_date = date(full_year, month + 1, 1)
    # Go back one day to get last day of expiration month
    from datetime import timedelta
    expiration_date = expiration_date - timedelta(days=1)

    # Calculate days remaining
    today = date.today()
    days_remaining = (expiration_date - today).days

    # Create license info
    license_info = LicenseInfo(
        client_id=client_id,
        expiration_date=expiration_date,
        is_valid=days_remaining >= 0,
        days_remaining=days_remaining,
        raw_key=key
    )

    if days_remaining < 0:
        return False, license_info, f"Licencia expirada hace {abs(days_remaining)} días"

    return True, license_info, None


def get_license_file_path() -> Path:
    """Get the path to the license file."""
    return get_data_dir() / LICENSE_FILE


def save_license(key: str) -> bool:
    """
    Save a license key to the license file.

    Args:
        key: License key to save

    Returns:
        True if saved successfully
    """
    try:
        license_path = get_license_file_path()
        license_path.write_text(key.strip().upper())
        return True
    except Exception:
        return False


def load_license() -> Optional[str]:
    """
    Load the license key from the license file.

    Returns:
        License key string if exists, None otherwise
    """
    try:
        license_path = get_license_file_path()
        if license_path.exists():
            return license_path.read_text().strip()
    except Exception:
        pass
    return None


def get_current_license() -> Tuple[bool, Optional[LicenseInfo], Optional[str]]:
    """
    Get and validate the current saved license.

    Returns:
        Tuple of (is_valid, license_info, error_message)
    """
    key = load_license()
    if not key:
        return False, None, "No hay licencia activada"

    return validate_license_key(key)


def clear_license() -> bool:
    """
    Remove the saved license.

    Returns:
        True if removed successfully
    """
    try:
        license_path = get_license_file_path()
        if license_path.exists():
            license_path.unlink()
        return True
    except Exception:
        return False


def get_current_license_with_online() -> Tuple[bool, Optional[LicenseInfo], Optional[str]]:
    """
    Get and validate the current license, including online validation.

    Logic:
    1. Validate offline first (existing logic). If invalid, return immediately.
    2. If no license.meta exists → pure offline mode (backwards compat).
    3. If meta exists and >30 days since last check → try online validation.
    4. If online fails but within grace period (60 days total) → allow.
    5. If online fails and beyond grace period → block.
    6. Any unexpected exception → fallback to offline (never break).

    Returns:
        Tuple of (is_valid, license_info, error_message)
    """
    # Step 1: Offline validation
    is_valid, license_info, error = get_current_license()
    if not is_valid:
        return is_valid, license_info, error

    # Step 2-6: Online checks
    try:
        from .license_online import (
            load_metadata, needs_online_validation,
            validate_online, is_within_grace_period
        )

        meta = load_metadata()

        # Case A: Never activated online = pure offline license
        if not meta or not meta.activated_online:
            license_info.online_status = "offline_only"
            return True, license_info, None

        # Populate online fields from metadata
        if meta.last_validated_online:
            license_info.last_online_check = meta.last_validated_online
        if meta.slot is not None and meta.max_slots is not None:
            license_info.machine_slot = f"{meta.slot}/{meta.max_slots}"

        # Case B: Check if periodic validation needed
        if needs_online_validation():
            key = load_license()
            ok, err_msg = validate_online(key)
            if ok:
                license_info.online_status = "ok"
                # Reload metadata after successful validation
                meta = load_metadata()
                if meta:
                    license_info.last_online_check = meta.last_validated_online
                    if meta.slot is not None and meta.max_slots is not None:
                        license_info.machine_slot = f"{meta.slot}/{meta.max_slots}"
                return True, license_info, None
            else:
                # Validation failed — check grace period
                if is_within_grace_period():
                    license_info.online_status = "grace_period"
                    return True, license_info, None
                else:
                    license_info.online_status = "revoked"
                    license_info.is_valid = False
                    return False, license_info, err_msg
        else:
            # Within validation interval, no check needed
            # But still verify grace period hasn't expired
            if not is_within_grace_period():
                license_info.online_status = "revoked"
                license_info.is_valid = False
                return False, license_info, "License validation expired"

            license_info.online_status = "ok"
            return True, license_info, None

    except Exception:
        # If online module fails for any reason, fall back to offline
        if license_info:
            license_info.online_status = "offline_only"
        return True, license_info, None
