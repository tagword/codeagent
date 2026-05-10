"""Configuration management for CodeAgent"""
import os
import logging
from typing import Any, Dict, Optional
logger = logging.getLogger(__name__)

class Config:
    """Configuration management class."""
    
    def __init__(self, **kwargs):
        # Load defaults
        defaults = load_defaults()
        
        # Override with file config
        file_config = load_from_file(CONFIG_FILE)
        defaults.update(file_config)
        
        # Override with environment
        env_config = load_from_env()
        defaults.update(env_config)
        
        # Override with kwargs
        defaults.update(kwargs)
        
        # Set as instance attributes
        self._values = defaults
        self._update_from_env(kwargs)
    
    def _update_from_env(self, overrides: Dict[str, Any]):
        """Update config with provided overrides."""
        for key, value in overrides.items():
            if key in self._values:
                self._values[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self._values.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value.
        
        Arguments:
            key: Configuration key
            value: Value to set
        """
        self._values[key] = value
    
    @property
    def max_turns(self) -> int:
        return self._values.get("max_turns", 8)
    
    @property
    def token_budget(self) -> int:
        return self._values.get("token_budget", 2000)
    
    @property
    def session_dir(self) -> str:
        return self._values.get("session_dir", DEFAULTS["session_dir"])
    
    @property
    def auto_save(self) -> bool:
        return self._values.get("auto_save", True)
    
    @property
    def compact_after(self) -> int:
        return self._values.get("compact_after", 12)
    
    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary."""
        return self._values.copy()
    
    def __repr__(self) -> str:
        return f"Config({self._values})"
    
    @staticmethod
    def from_env() -> Config:
        """Create Config from environment and defaults."""
        return Config()
    
    @staticmethod
    def from_file(path: str) -> Config:
        """Create Config from file."""
        defaults = load_from_file(path)
        return Config(**defaults)

def save_config(config: Config, path: Optional[str] = None) -> None:
    """
    Save configuration to a YAML file.

    Arguments:
        config: Config object to save
        path: Optional path (default: CONFIG_FILE)
    """
    if path is None:
        path = CONFIG_FILE
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    # Write YAML
    data = config.to_dict()
    if yaml is None:
        raise RuntimeError("PyYAML is required to save config")
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)
