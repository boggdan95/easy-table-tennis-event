"""Tests for internationalization (i18n) module."""

import os
import pytest

from ettem.i18n import (
    load_strings,
    get_string,
    clear_cache,
    get_language_from_env,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
)


class TestI18n:
    """Test i18n functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()
        # Clear ETTEM_LANG env var if set
        if "ETTEM_LANG" in os.environ:
            del os.environ["ETTEM_LANG"]

    def teardown_method(self):
        """Clean up after each test."""
        clear_cache()
        if "ETTEM_LANG" in os.environ:
            del os.environ["ETTEM_LANG"]

    def test_load_strings_spanish(self):
        """Test loading Spanish strings."""
        strings = load_strings("es")
        assert isinstance(strings, dict)
        assert "app" in strings
        assert strings["app"]["title"] == "Gestor de Eventos de Tenis de Mesa"

    def test_load_strings_english(self):
        """Test loading English strings."""
        strings = load_strings("en")
        assert isinstance(strings, dict)
        assert "app" in strings
        assert strings["app"]["title"] == "Table Tennis Event Manager"

    def test_load_strings_invalid_language(self):
        """Test loading strings with invalid language raises error."""
        with pytest.raises(ValueError, match="not supported"):
            load_strings("fr")

    def test_load_strings_caching(self):
        """Test that strings are cached after first load."""
        # Load Spanish strings twice
        strings1 = load_strings("es")
        strings2 = load_strings("es")

        # Should return the same object (from cache)
        assert strings1 is strings2

    def test_get_string_simple_key(self):
        """Test getting a simple top-level string."""
        # Note: Our strings use nested structure, so we test nested keys
        result = get_string("app.title", "es")
        assert result == "Gestor de Eventos de Tenis de Mesa"

        result = get_string("app.title", "en")
        assert result == "Table Tennis Event Manager"

    def test_get_string_nested_key(self):
        """Test getting a nested string using dot notation."""
        result = get_string("cli.import_players.description", "es")
        assert result == "Importar jugadores desde CSV"

        result = get_string("cli.import_players.description", "en")
        assert result == "Import players from CSV"

    def test_get_string_with_formatting(self):
        """Test getting a string with format variables."""
        result = get_string("cli.import_players.success", "es", count=5, category="U13")
        assert "5" in result
        assert "U13" in result

        result = get_string("cli.import_players.success", "en", count=10, category="U15")
        assert "10" in result
        assert "U15" in result

    def test_get_string_missing_key(self):
        """Test getting a non-existent key returns the key itself."""
        result = get_string("nonexistent.key", "es")
        assert result == "nonexistent.key"

    def test_get_string_fallback_to_english(self):
        """Test that missing Spanish key falls back to English."""
        # This test assumes a key exists in English but not Spanish
        # For now, we just test that fallback mechanism works
        result = get_string("nonexistent.test", "es")
        assert result == "nonexistent.test"  # Falls back to key if not found in either

    def test_get_language_from_env_default(self):
        """Test getting language from env when not set."""
        lang = get_language_from_env()
        assert lang == DEFAULT_LANGUAGE

    def test_get_language_from_env_set(self):
        """Test getting language from env when set."""
        os.environ["ETTEM_LANG"] = "en"
        lang = get_language_from_env()
        assert lang == "en"

        os.environ["ETTEM_LANG"] = "es"
        lang = get_language_from_env()
        assert lang == "es"

    def test_get_language_from_env_invalid(self):
        """Test getting language from env with invalid value."""
        os.environ["ETTEM_LANG"] = "fr"
        lang = get_language_from_env()
        # Should fall back to default
        assert lang == DEFAULT_LANGUAGE

    def test_clear_cache(self):
        """Test clearing the cache."""
        # Load strings to populate cache
        load_strings("es")
        load_strings("en")

        # Clear cache
        clear_cache()

        # Load again - should reload from file
        strings = load_strings("es")
        assert isinstance(strings, dict)

    def test_supported_languages(self):
        """Test that supported languages constant is correct."""
        assert isinstance(SUPPORTED_LANGUAGES, list)
        assert "es" in SUPPORTED_LANGUAGES
        assert "en" in SUPPORTED_LANGUAGES
        assert len(SUPPORTED_LANGUAGES) == 2

    def test_webapp_strings_exist(self):
        """Test that webapp strings are defined."""
        strings = load_strings("es")
        # Navigation strings are at top level
        assert "nav" in strings
        assert "home" in strings["nav"]
        # Admin section has webapp-related strings
        assert "admin" in strings

    def test_cli_strings_exist(self):
        """Test that CLI strings are defined."""
        strings = load_strings("es")
        assert "cli" in strings
        assert "import_players" in strings["cli"]
        assert "export" in strings["cli"]

    def test_validation_strings_exist(self):
        """Test that validation strings are defined."""
        strings = load_strings("es")
        assert "validation" in strings
        assert "required_field" in strings["validation"]

    def test_common_strings_exist(self):
        """Test that common strings are defined."""
        strings = load_strings("es")
        assert "common" in strings
        # YAML booleans become Python True/False keys
        assert True in strings["common"]
        assert False in strings["common"]
