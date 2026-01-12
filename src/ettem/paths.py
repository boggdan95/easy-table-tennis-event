"""
Path utilities for ETTEM - handles both development and PyInstaller frozen modes.
"""

import sys
import os
from pathlib import Path


def is_frozen() -> bool:
    """Check if running as a PyInstaller frozen executable."""
    return getattr(sys, 'frozen', False)


def get_base_path() -> Path:
    """
    Get the base path for the application.

    Returns:
        - When frozen (exe): The temporary _MEIPASS directory where PyInstaller extracts files
        - When running as script: The project root directory
    """
    if is_frozen():
        # Running as compiled executable - use PyInstaller's temp directory
        return Path(sys._MEIPASS)
    else:
        # Running as script - go up from src/ettem/ to project root
        return Path(__file__).parent.parent.parent


def get_i18n_dir() -> Path:
    """Get the i18n directory path."""
    return get_base_path() / "i18n"


def get_templates_dir() -> Path:
    """Get the templates directory path."""
    if is_frozen():
        return get_base_path() / "ettem" / "webapp" / "templates"
    else:
        return Path(__file__).parent / "webapp" / "templates"


def get_static_dir() -> Path:
    """Get the static files directory path."""
    if is_frozen():
        return get_base_path() / "ettem" / "webapp" / "static"
    else:
        return Path(__file__).parent / "webapp" / "static"


def get_config_dir() -> Path:
    """Get the config directory path."""
    return get_base_path() / "config"


def get_data_dir() -> Path:
    """
    Get the user data directory for storing database and user files.

    Returns:
        Path to .ettem/ directory in user's home or current directory
    """
    # Always use .ettem in current working directory for portability
    data_dir = Path.cwd() / ".ettem"
    data_dir.mkdir(exist_ok=True)
    return data_dir
