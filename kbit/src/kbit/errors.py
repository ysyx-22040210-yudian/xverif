class KbitError(Exception):
    """Base error with a stable JSON error code."""

    code = "KBIT_ERROR"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = {k: v for k, v in details.items() if v is not None}

    def to_error(self) -> dict:
        error = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return error


class ParseError(KbitError):
    code = "PARSE_ERROR"


class WidthError(KbitError):
    code = "WIDTH_OUT_OF_RANGE"


class ValueError2State(KbitError):
    code = "FOUR_STATE_LITERAL"


class FourStateUnsupported(KbitError):
    code = "FOUR_STATE_UNSUPPORTED"


class UnknownVariable(KbitError):
    code = "UNKNOWN_VARIABLE"


class EvalError(KbitError):
    code = "EVAL_ERROR"


class DivisionByZero(KbitError):
    code = "DIVISION_BY_ZERO"
