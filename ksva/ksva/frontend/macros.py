"""宏检测。对齐 spec 13.3。

检测 Verilog preprocessor 指令。ksva 不负责宏展开。
"""

from __future__ import annotations

from ksva.ir.common import DiagnosticIR, Severity, SourceSpan

# 可检测的宏指令
_MACRO_KEYWORDS = [
    "`define", "`ifdef", "`ifndef", "`elsif", "`else", "`endif",
    "`include", "`undef",
]


def detect_macros(src: str, file: str = "<unknown>") -> list[DiagnosticIR]:
    """检测源码中的 preprocessor 宏，返回 KSVA-W009 诊断信息。

    每遇到一行以 ` 开头的预处理指令就记录一条 warning。
    """
    diagnostics: list[DiagnosticIR] = []
    lines = src.split("\n")

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("`"):
            continue

        for kw in _MACRO_KEYWORDS:
            if stripped.startswith(kw):
                diagnostics.append(DiagnosticIR(
                    code="KSVA-W009",
                    severity=Severity.WARNING.value,
                    message=f"Macro detected: {stripped}. Preprocess source for accurate parsing.",
                    span=SourceSpan(file=file, begin_line=line_no, begin_col=1,
                                    end_line=line_no, end_col=len(line)),
                ))
                break

    return diagnostics
