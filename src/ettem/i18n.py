"""Internationalization utilities."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from ettem.paths import get_i18n_dir

# Cache for loaded strings to avoid repeated file I/O
_strings_cache: Dict[str, Dict[str, Any]] = {}

# Supported languages
SUPPORTED_LANGUAGES = ["es", "en"]
DEFAULT_LANGUAGE = "es"


def _get_i18n_dir() -> Path:
    """Get the i18n directory path (supports PyInstaller frozen mode)."""
    return get_i18n_dir()


def load_strings(lang: str) -> Dict[str, Any]:
    """
    Load strings from i18n/strings_{lang}.yaml.

    Args:
        lang: Language code (es, en)

    Returns:
        Dictionary with all strings for the given language

    Raises:
        ValueError: If language is not supported
        FileNotFoundError: If the strings file doesn't exist
    """
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Language '{lang}' not supported. Supported languages: {SUPPORTED_LANGUAGES}"
        )

    # Return from cache if already loaded
    if lang in _strings_cache:
        return _strings_cache[lang]

    # Load from file
    i18n_dir = _get_i18n_dir()
    strings_file = i18n_dir / f"strings_{lang}.yaml"

    if not strings_file.exists():
        raise FileNotFoundError(f"Strings file not found: {strings_file}")

    with open(strings_file, "r", encoding="utf-8") as f:
        strings = yaml.safe_load(f)

    # Cache the loaded strings
    _strings_cache[lang] = strings or {}

    return _strings_cache[lang]


def get_string(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Get a string by key for the specified language.

    Supports dot notation for nested keys (e.g., "cli.import_players.success").

    Args:
        key: String key (supports dot notation for nested keys)
        lang: Language code (es, en)
        **kwargs: Format variables to substitute in the string

    Returns:
        The translated string, or the key itself if not found

    Examples:
        >>> get_string("app.title", "es")
        "Gestor de Eventos de Tenis de Mesa"
        >>> get_string("cli.import.success", "en", count=5)
        "Successfully imported 5 players"
    """
    try:
        strings = load_strings(lang)
    except (ValueError, FileNotFoundError) as e:
        # If we can't load strings, try fallback to default language
        if lang != DEFAULT_LANGUAGE:
            try:
                strings = load_strings(DEFAULT_LANGUAGE)
            except (ValueError, FileNotFoundError):
                return key
        else:
            return key

    # Navigate through nested keys using dot notation
    value = strings
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            # Key not found, try fallback to English if we're not already there
            if lang != "en":
                try:
                    en_strings = load_strings("en")
                    en_value = en_strings
                    for en_part in key.split("."):
                        if isinstance(en_value, dict) and en_part in en_value:
                            en_value = en_value[en_part]
                        else:
                            return key
                    value = en_value
                    break
                except (ValueError, FileNotFoundError):
                    return key
            else:
                return key

    # If the final value is not a string, return the key
    if not isinstance(value, str):
        return key

    # Format the string with kwargs if provided
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, ValueError):
            # If formatting fails, return the unformatted string
            return value

    return value


def clear_cache() -> None:
    """Clear the strings cache. Useful for testing or reloading strings."""
    _strings_cache.clear()


def get_language_from_env() -> str:
    """
    Get the language from environment variable ETTEM_LANG.

    Returns:
        Language code (defaults to DEFAULT_LANGUAGE if not set or invalid)
    """
    env_lang = os.environ.get("ETTEM_LANG", DEFAULT_LANGUAGE)
    if env_lang in SUPPORTED_LANGUAGES:
        return env_lang
    return DEFAULT_LANGUAGE
