"""Package: config_plane_pkg"""
from src.config_plane_pkg._config_plane_pkg_merged import build_system_prompt
from src.config_plane_pkg._config_plane_pkg_merged import ensure_default_config_files
from src.config_plane_pkg._config_plane_pkg_merged import (
    CONFIG_FILENAMES,
    project_root,
    config_dir,
    _read_if_exists,
    _plugin_skill_appendices,
    _ensure_default_codeagent_cron_json,
    materialize_codeagent_cron_json,
)
