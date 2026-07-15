"""ksva lint 模块 — 静态规则检查。对齐 spec 第十九章。

规则表:
  KSVA-W001  missing disable iff
  KSVA-W002  antecedent is constant false (vacuous)
  KSVA-W003  antecedent is constant true
  KSVA-W004  large delay range
  KSVA-W005  unbounded delay
  KSVA-W006  advanced construct detected
  KSVA-W007  local variable update inside repetition
  KSVA-W008  multi-clock property
  KSVA-W009  macro detected
  KSVA-W010  unsupported assignment form
"""

from __future__ import annotations

from ksva.ir.common import DiagnosticIR
from ksva.ir.timeline import TimelineIR

from . import vacuity, temporal, local_var


def lint_timeline(
    timeline: TimelineIR,
    surface_ir=None,
) -> list[DiagnosticIR]:
    """对 TimelineIR 执行所有 lint 规则，返回诊断列表。"""
    results: list[DiagnosticIR] = []

    results.extend(vacuity.check(timeline))
    results.extend(temporal.check(timeline))
    results.extend(local_var.check(timeline))

    if surface_ir:
        from ksva.frontend.macros import detect_macros
        if hasattr(surface_ir, 'raw_text'):
            results.extend(detect_macros(surface_ir.raw_text))

    return results
