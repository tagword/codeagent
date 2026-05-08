"""Smoke tests — verify the project loads without import errors."""


def test_import_main_package():
    """codeagent top-level packages can be imported."""
    import codeagent  # noqa: F401
    import seed  # noqa: F401


def test_import_key_modules():
    """Core modules can be imported."""
    import seed.engine  # noqa: F401
    import seed.execution  # noqa: F401
    import seed.routing  # noqa: F401
    import seed_services.safety  # noqa: F401
