from __future__ import annotations


class XentryError(Exception):
    code = "XENTRY_ERROR"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


class ConfigError(XentryError):
    code = "INVALID_CONFIG"


class UnsupportedConfigField(ConfigError):
    code = "UNSUPPORTED_CONFIG_FIELD"


class FragmentError(XentryError):
    code = "INVALID_FRAGMENT"


class RequestError(XentryError):
    code = "INVALID_REQUEST"


class JsonError(RequestError):
    code = "INVALID_JSON"
