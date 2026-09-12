"""
Custom exception hierarchy. Routers raise these; main.py registers handlers
that translate them into consistent JSON error responses. Keeps HTTP-status
decisions out of the service layer.
"""


class AICAException(Exception):
    """Base class for all application-raised exceptions."""
    status_code: int = 500
    detail: str = "An unexpected error occurred."

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class InvalidUploadError(AICAException):
    status_code = 400
    detail = "The uploaded file is invalid."


class UploadTooLargeError(AICAException):
    status_code = 400
    detail = "The uploaded file exceeds the configured size limit."


class UnsafeArchiveError(AICAException):
    """Raised when a ZIP entry would extract outside the target directory
    (zip-slip) or otherwise looks unsafe."""
    status_code = 400
    detail = "The archive contains unsafe paths and was rejected."


class RepositoryNotFoundError(AICAException):
    status_code = 404
    detail = "Repository not found."


class NotImplementedFeatureError(AICAException):
    """Used for endpoints belonging to a phase that hasn't landed yet.
    Distinct from a generic 500 so the frontend can render an honest
    'not available yet' state rather than a crash."""
    status_code = 501
    detail = "This feature is not implemented yet."
