"""时序检查规则。对齐 spec 第十九章。

KSVA-W004: large delay range (> 32 or user configured)
KSVA-W005: unbounded delay ($)
KSVA-W006: advanced construct (first_match, throughout, intersect, within)
KSVA-W008: multi-clock property
"""

from __future__ import annotations

from ksva.ir.common import DiagnosticIR, Severity
from ksva.ir.timeline import ObligationKind, TimelineIR

LARGE_DELAY_THRESHOLD = 32


def check(timeline: TimelineIR) -> list[DiagnosticIR]:
    results: list[DiagnosticIR] = []

    for ob in timeline.obligations:
        # W004: large delay range
        if ob.window:
            span = ob.window.end - ob.window.start if not ob.window.unbounded else 9999
            if span > LARGE_DELAY_THRESHOLD:
                results.append(DiagnosticIR(
                    code="KSVA-W004",
                    severity=Severity.WARNING,
                    message=f"Large delay range [{ob.window.start}:{ob.window.end}] "
                            f"may create many candidate match paths.",
                ))

        # W005: unbounded delay
        if ob.window and ob.window.unbounded:
            results.append(DiagnosticIR(
                code="KSVA-W005",
                severity=Severity.WARNING,
                message="Unbounded delay cannot be represented as a finite timeline.",
            ))

    # W006: advanced construct detected
    for path in timeline.match_paths:
        for ob in path.obligations:
            if ob.kind == ObligationKind.SEQUENCE_PATH:
                results.append(DiagnosticIR(
                    code="KSVA-W006",
                    severity=Severity.WARNING,
                    message=f"Advanced SVA construct detected in obligation {ob.id}. "
                            f"Timeline lowering may be partial.",
                ))
                break

    return results
