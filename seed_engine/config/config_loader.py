from __future__ import annotations
"""Configuration management for CodeAgent"""
import os
import logging
from typing import Any, Dict, Optional
logger = logging.getLogger(__name__)

# Configuration management for CodeAgent
# Handles loading YAML config and environment variables

import os
from typing import Optional, Dict, Any

try:
    import yaml
except ImportError:  # PyYAML optional for minimal install
    yaml = None  # type: ignore

# Default configuration
DEFAULTS = {
    'max_turns': 8,
    'token_budget': 2000,
    'session_dir': '~/.codeagent/sessions',
    'auto_save': True,
    'compact_after': 12,
}

CONFIG_FILE = os.path.expanduser("~/.codeagent/config.yaml")

def load_config() -> Dict[str, Any]:
    """
    Load configuration from file and environment variables.
    
    Returns:
        Dictionary with configuration values
    """
    config = load_defaults()
    
    # Load from config file if it exists
    if os.path.exists(CONFIG_FILE):
        file_config = load_from_file(CONFIG_FILE)
        config.update(file_config)
    
    # Load from environment variables (overrides file)
    env_config = load_from_env()
    config.update(env_config)
    
    return config

def load_defaults() -> Dict[str, Any]:
    """Load default configuration values."""
    return DEFAULTS.copy()

def load_from_file(path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.
    
    Arguments:
        path: Path to the YAML config file
        
    Returns:
        Dictionary with config values from file
    """
    if not os.path.exists(path):
        return {}
    
    if yaml is None:
        print("Warning: PyYAML not installed; skipping config file load.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception as e:
        print(f"Warning: Failed to load config from {path}: {e}")
        return {}

def load_from_env() -> Dict[str, Any]:
    """
    Load configuration from environment variables.
    
    Environment variable prefixes and defaults:
        CODEAGENT_MAX_TURNS (default: 8)
        CODEAGENT_TOKEN_BUDGETT (default: 2000)
        CODEAGENT_SESSION_DIR (default: ~/.codeagent/sessions)
        CODEAGENT_AUTO_SAVE (default: true)
    
    Returns:
        Dictionary with environment-based config values
    """
    env = {}
    
    # Read max_turns
    env_max_turns = os.environ.get("CODEAGENT_MAX_TURNS")
    if env_max_turns:
        try:
            env['max_turns'] = int(env_max_turns)
        except ValueError:
            pass
    
    # Read token_budget
    env_budget = os.environ.get("CODEAGENT_TOKEN_BUDGET")
    if env_budget:
        try:
            env['token_budget'] = int(env_budget)
        except ValueError:
            pass
    
    # Read session_dir
    env_dir = os.environ.get("CODEAGENT_SESSION_DIR")
    if env_dir:
        env['session_dir'] = env_dir
    
    # Read auto_save
    env_auto = os.environ.get("CODEAGENT_AUTO_SAVE")
    if env_auto:
        env['auto_save'] = env_auto.lower() == "true"
    
    return env

