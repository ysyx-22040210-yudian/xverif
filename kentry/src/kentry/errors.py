from __future__ import annotations


class KentryError(Exception):
    code = "KENTRY_ERROR"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


class ConfigError(KentryError):
    code = "INVALID_CONFIG"


class UnsupportedConfigField(ConfigError):
    code = "UNSUPPORTED_CONFIG_FIELD"


class FragmentError(KentryError):
    code = "INVALID_FRAGMENT"


class RequestError(KentryError):
    code = "INVALID_REQUEST"


class JsonError(RequestError):
    code = "INVALID_JSON"
