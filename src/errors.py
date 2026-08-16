# src/errors.py
ERROR_STATUS = {
    "unauthorized": 401,
    "payload_too_large": 413,
    "invalid_json": 400,
    "invalid_diff": 422,
    "idempotency_conflict": 409,
    "not_found": 404,
    "rate_limited": 429,
    "internal": 500,
}

class APIError(Exception):
    def __init__(self, code: str, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = ERROR_STATUS[code]
        self.headers = headers or {}