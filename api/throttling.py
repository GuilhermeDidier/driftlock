"""Per-client rate limits.

The global spend cap is the backstop; these keep one visitor from consuming
the whole day's budget before anyone else arrives.
"""
from rest_framework.throttling import AnonRateThrottle


class RunThrottle(AnonRateThrottle):
    """Triggering a run is the only request that can cost money."""

    scope = "run"


class LayoutThrottle(AnonRateThrottle):
    """Flipping the storefront is free, but it is still a write."""

    scope = "layout"
