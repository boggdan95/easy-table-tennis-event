"""
Machine identification for ETTEM license binding.

Generates a stable, unique hardware-based ID for each device.
- Windows: motherboard serial + BIOS serial + volume serial
- macOS: Hardware UUID + serial number
- Fallback: hostname + username
"""

import hashlib
import platform
import subprocess
import getpass


def _run_command(cmd: list[str], timeout: int = 5) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


def _get_windows_ids() -> list[str]:
    """Get hardware identifiers on Windows."""
    parts = []

    # Motherboard serial (very stable, survives OS reinstalls)
    output = _run_command(["wmic", "baseboard", "get", "serialnumber"])
    lines = [l.strip() for l in output.split("\n") if l.strip() and l.strip().lower() != "serialnumber"]
    if lines and lines[0].lower() not in ("to be filled by o.e.m.", "default string", "none", ""):
        parts.append(f"mb:{lines[0]}")

    # BIOS serial
    output = _run_command(["wmic", "bios", "get", "serialnumber"])
    lines = [l.strip() for l in output.split("\n") if l.strip() and l.strip().lower() != "serialnumber"]
    if lines and lines[0].lower() not in ("to be filled by o.e.m.", "default string", "none", ""):
        parts.append(f"bios:{lines[0]}")

    # Volume serial of C: drive
    output = _run_command(["wmic", "logicaldisk", "where", "DeviceID='C:'", "get", "VolumeSerialNumber"])
    lines = [l.strip() for l in output.split("\n") if l.strip() and l.strip().lower() != "volumeserialnumber"]
    if lines and lines[0]:
        parts.append(f"vol:{lines[0]}")

    return parts


def _get_macos_ids() -> list[str]:
    """Get hardware identifiers on macOS."""
    parts = []

    output = _run_command(["system_profiler", "SPHardwareDataType"], timeout=10)
    for line in output.split("\n"):
        line = line.strip()
        if "Hardware UUID" in line:
            uuid = line.split(":")[-1].strip()
            if uuid:
                parts.append(f"hwuuid:{uuid}")
        elif "Serial Number" in line:
            serial = line.split(":")[-1].strip()
            if serial:
                parts.append(f"serial:{serial}")

    return parts


def get_machine_id() -> str:
    """
    Generate a stable machine ID based on hardware identifiers.

    Returns:
        64-character hex string (SHA-256 hash)
    """
    system = platform.system()

    if system == "Windows":
        parts = _get_windows_ids()
    elif system == "Darwin":
        parts = _get_macos_ids()
    else:
        parts = []

    # Fallback if no hardware IDs found
    if not parts:
        parts.append(f"host:{platform.node()}")
        parts.append(f"user:{getpass.getuser()}")

    combined = "|".join(sorted(parts))
    return hashlib.sha256(combined.encode()).hexdigest()


def get_machine_label() -> str:
    """
    Get a human-readable label for this machine.

    Returns:
        String like "DESKTOP-ABC / Windows 11"
    """
    hostname = platform.node()
    os_info = f"{platform.system()} {platform.release()}"
    return f"{hostname} / {os_info}"
