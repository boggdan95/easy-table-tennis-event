"""Configuration loader and validator."""

from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Configuration validation error."""

    pass


def load_config(path: str) -> dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        path: Path to YAML config file

    Returns:
        Dictionary with configuration values

    Raises:
        ConfigError: If file not found or invalid YAML
    """
    config_file = Path(path)

    if not config_file.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")

    if config is None:
        raise ConfigError("Config file is empty")

    return config


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate configuration values.

    Args:
        config: Configuration dictionary

    Returns:
        Validated and normalized configuration

    Raises:
        ConfigError: If validation fails
    """
    validated = {}

    # Random seed (optional, default 42)
    validated["random_seed"] = config.get("random_seed", 42)
    if not isinstance(validated["random_seed"], int):
        raise ConfigError("random_seed must be an integer")

    # Group size preference (required, must be 3 or 4)
    if "group_size_preference" not in config:
        raise ConfigError("Missing required field: group_size_preference")

    group_size = config["group_size_preference"]
    if group_size not in (3, 4):
        raise ConfigError(f"group_size_preference must be 3 or 4, got {group_size}")
    validated["group_size_preference"] = group_size

    # Advance per group (optional, default 2)
    validated["advance_per_group"] = config.get("advance_per_group", 2)
    if not isinstance(validated["advance_per_group"], int) or validated["advance_per_group"] < 1:
        raise ConfigError("advance_per_group must be a positive integer")

    # Language (optional, default 'es')
    lang = config.get("lang", "es")
    if lang not in ("es", "en"):
        raise ConfigError(f"lang must be 'es' or 'en', got '{lang}'")
    validated["lang"] = lang

    # Scheduling (V1 not implemented, but accept the field)
    if "scheduling" in config:
        if not isinstance(config["scheduling"], dict):
            raise ConfigError("scheduling must be a dictionary")
        if config["scheduling"].get("enabled", False):
            print("WARNING: scheduling is not implemented in V1, ignoring enabled=true")
        validated["scheduling"] = config["scheduling"]
    else:
        validated["scheduling"] = {"enabled": False}

    return validated


def load_and_validate_config(path: str) -> dict[str, Any]:
    """Load and validate configuration in one step.

    Args:
        path: Path to YAML config file

    Returns:
        Validated configuration dictionary

    Raises:
        ConfigError: If loading or validation fails
    """
    config = load_config(path)
    return validate_config(config)
