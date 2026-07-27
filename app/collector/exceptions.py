from __future__ import annotations


class CollectorError(Exception):
    """Base exception for all collector errors."""


class CollectorAuthError(CollectorError):
    """Authentication failed with the data source."""


class CollectorRateLimitError(CollectorError):
    """Rate limit exceeded."""

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after}s"
            if retry_after
            else "Rate limit exceeded"
        )


class CollectorNetworkError(CollectorError):
    """Network error connecting to data source."""


class CollectorNotFoundError(CollectorError):
    """Requested resource not found."""


class CollectorValidationError(CollectorError):
    """Invalid response format from data source."""


class CollectorConfigError(CollectorError):
    """Configuration error for collector."""
