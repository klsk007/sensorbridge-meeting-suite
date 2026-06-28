from __future__ import annotations

from typing import Any

from bridgeclient.models import error_json


class BridgeClientError(RuntimeError):
    """Base exception rendered by the CLI as a JSON error payload."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "bridge_error",
        detail: Any | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail
        self.status = status

    def to_json(self) -> dict[str, Any]:
        detail = self.detail
        if self.status is not None:
            if isinstance(detail, dict):
                detail = {**detail, "status": self.status}
            else:
                detail = {"detail": detail, "status": self.status}
        return error_json(self.code, self.message, detail=detail)
