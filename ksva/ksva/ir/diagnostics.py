"""诊断收集器 DiagnosticBag。"""

from __future__ import annotations

from .common import DiagnosticIR, Severity


class DiagnosticBag:
    """收集解析/编译过程中产生的诊断信息。"""

    def __init__(self) -> None:
        self.diagnostics: list[DiagnosticIR] = []

    def add(self, diag: DiagnosticIR) -> None:
        self.diagnostics.append(diag)

    def info(self, code: str, message: str) -> None:
        self.add(DiagnosticIR(code=code, severity=Severity.INFO, message=message))

    def warning(self, code: str, message: str) -> None:
        self.add(DiagnosticIR(code=code, severity=Severity.WARNING, message=message))

    def error(self, code: str, message: str) -> None:
        self.add(DiagnosticIR(code=code, severity=Severity.ERROR, message=message))

    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)

    def has_warnings(self) -> bool:
        return any(d.severity == Severity.WARNING for d in self.diagnostics)

    def errors(self) -> list[DiagnosticIR]:
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    def warnings(self) -> list[DiagnosticIR]:
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]
