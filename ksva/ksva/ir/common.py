"""公共 IR 定义：SourceSpan, LoweringStatus, DiagnosticIR.

对齐 spec 第七章。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceSpan:
    """源码位置。"""

    file: str = ""
    begin_line: int = 0
    begin_col: int = 0
    end_line: int = 0
    end_col: int = 0


@enum.unique
class LoweringStatus(str, enum.Enum):
    """lowering 精度状态。

    对齐 spec 7.2：exact → partial → opaque → unsupported → unsafe_to_explain。
    """

    EXACT = "exact"
    PARTIAL = "partial"
    OPAQUE = "opaque"
    UNSUPPORTED = "unsupported"
    UNSAFE_TO_EXPLAIN = "unsafe_to_explain"


@enum.unique
class Severity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class DiagnosticIR:
    """诊断信息。对齐 spec 7.3。

    severity: info / warning / error.
    """

    code: str
    severity: str
    message: str
    span: SourceSpan = field(default_factory=SourceSpan)
