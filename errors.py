from enum import Enum
from typing import Any


class ErrorCode(Enum):
    FILE_NOT_FOUND = "file_not_found"
    PERMISSION_DENIED = "permission_denied"
    INVALID_PATH = "invalid_path"
    FILE_TOO_LARGE = "file_too_large"
    INVALID_REGEX = "invalid_regex"
    GIT_ERROR = "git_error"
    SUBPROCESS_ERROR = "subprocess_error"
    FUNCTION_NOT_FOUND = "function_not_found"
    MAX_ITERATIONS = "max_iterations_reached"


class AgentError(Exception):
    """Base error with structured context for AI consumption."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        suggestions: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.suggestions = suggestions or []
        self.context = context or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for AI consumption."""
        return {
            "error_code": self.code.value,
            "message": self.message,
            "suggestions": self.suggestions,
            "context": self.context,
        }

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


class FileError(AgentError):
    """File operation errors."""

    pass


class GitError(AgentError):
    """Git operation errors."""

    pass


class SearchError(AgentError):
    """Search operation errors."""

    pass
