"""Bridge ``CODEAGENT_*`` process env into ``SEED_*`` for the Seed kernel."""

from __future__ import annotations

import os


def bridge_codeagent_env_to_seed() -> None:
    """
    For each ``CODEAGENT_<SUFFIX>`` set in ``os.environ``, copy to ``SEED_<SUFFIX>``
    when the latter is not already defined.

    Call after loading ``config/seed.env`` (or legacy ``codeagent.env``) and before
    invoking Seed / seed-tools. Does not remove ``CODEAGENT_*`` keys.
    """
    for key, value in list(os.environ.items()):
        if not key.startswith("CODEAGENT_"):
            continue
        seed_key = "SEED_" + key[len("CODEAGENT_") :]
        if seed_key not in os.environ:
            os.environ[seed_key] = value
