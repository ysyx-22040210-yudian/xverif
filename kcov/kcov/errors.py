from __future__ import annotations

from typing import Any, Dict

Json = Dict[str, Any]


class KcovError(Exception):
    def __init__(self, code: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_json(self) -> Json:
        err: Json = {"code": self.code, "message": self.message}
        for key, value in self.detail.items():
            err[f"detail.{key}"] = value
        return err


def error_response(response_action: str, response_request_id: str, error_code: str, error_message: str,
                   **detail: Any) -> Json:
    err = KcovError(error_code, error_message, **detail)
    return {
        "ok": False,
        "api_version": "kcov.v1",
        "request_id": response_request_id,
        "action": response_action,
        "summary": {
            "matched_count": 0,
            "returned": 0,
            "truncated": False,
            "output_path": None,
        },
        "error": err.to_json(),
        "warnings": [],
    }
