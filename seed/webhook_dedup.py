# Re-export: seed → seed_services
from seed_services.webhook_dedup import (  # noqa: F401
    compute_webhook_dedup_key,
    dedup_enabled,
    reset_webhook_dedup_cache,
    try_acquire,
    try_acquire_report,
)
