"""Code Agent process bootstrap (product home → config → Seed bridge)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from codeagent.core.env import apply_default_product_home
from codeagent.core.seed_bridge import bridge_codeagent_env_to_seed
from seed.integrations.env_config import apply_seed_env_from_config


def bootstrap_codeagent_runtime(base: Optional[Path] = None) -> Path:
    """
    1. Default data root ``~/.codeagent`` (or ``CODEAGENT_HOME``)
    2. Set ``SEED_PROJECT_ROOT`` so Seed / seed-tools use the same tree
    3. Load ``config/seed.env`` + ``config/codeagent.env``
    4. Bridge ``CODEAGENT_*`` → ``SEED_*`` for kernel env keys
    """
    if base is not None:
        home = base.resolve()
        os.environ["CODEAGENT_HOME"] = str(home)
        os.environ["SEED_PROJECT_ROOT"] = str(home)
        home.mkdir(parents=True, exist_ok=True)
        (home / "config").mkdir(parents=True, exist_ok=True)
    else:
        home = apply_default_product_home()

    apply_seed_env_from_config(None)
    bridge_codeagent_env_to_seed()
    return home
