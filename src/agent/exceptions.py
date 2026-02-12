"""
Exception classes for agent errors.

Provides structured error types to distinguish between different failure modes
in extraction and search operations.
"""


class AgentError(Exception):
    """Base exception for agent errors"""
    pass


class ExtractionError(AgentError):
    """Failed to extract releases from email"""
    pass


class SearchError(AgentError):
    """Failed to search for album"""
    pass


class NoResultsError(AgentError):
    """No matches found (not an error, but explicit)"""
    pass


class InvalidResponseError(AgentError):
    """Agent returned invalid response"""
    pass
