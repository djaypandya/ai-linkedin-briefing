class BriefingError(Exception):
    """Base exception for expected agent failures."""


class ConfigurationError(BriefingError):
    """Raised when required configuration is missing or invalid."""


class SourceCollectionError(BriefingError):
    """Raised when source collection cannot produce valid candidates."""


class ValidationError(BriefingError):
    """Raised when drafts do not match the required contract."""


class PublishError(BriefingError):
    """Raised when browser publishing fails."""
