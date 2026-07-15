"""Lint 规则注册表。对齐 spec 第十九章。

诊断码表:
  KSVA-W001  missing disable iff
  KSVA-W002  antecedent is constant false
  KSVA-W003  antecedent is constant true
  KSVA-W004  large delay range
  KSVA-W005  unbounded delay
  KSVA-W006  advanced construct detected
  KSVA-W007  local variable update inside repetition
  KSVA-W008  multi-clock property
  KSVA-W009  macro detected
  KSVA-W010  unsupported assignment form
  KSVA-E001  failed to parse property
  KSVA-E002  property not found
  KSVA-E003  unbalanced parentheses
  KSVA-E004  top-level implication not found
"""

from __future__ import annotations

RULES: dict[str, dict] = {
    "KSVA-W001": {"severity": "warning", "msg": "Property has no disable iff. Reset behavior may be unclear."},
    "KSVA-W002": {"severity": "warning", "msg": "Antecedent is constant false. Assertion may be vacuous."},
    "KSVA-W003": {"severity": "warning", "msg": "Antecedent is constant true. Property starts a new attempt every cycle."},
    "KSVA-W004": {"severity": "warning", "msg": "Large delay range may create many candidate match paths."},
    "KSVA-W005": {"severity": "warning", "msg": "Unbounded delay cannot be represented as a finite timeline."},
    "KSVA-W006": {"severity": "warning", "msg": "Advanced SVA construct detected. Timeline lowering may be partial."},
    "KSVA-W007": {"severity": "warning", "msg": "Local variable update inside repetition creates path-dependent state."},
    "KSVA-W008": {"severity": "warning", "msg": "Multi-clock property is not fully supported."},
    "KSVA-W009": {"severity": "warning", "msg": "Macro detected. Preprocess source for accurate parsing."},
    "KSVA-W010": {"severity": "warning", "msg": "Unsupported assignment form."},
    "KSVA-E001": {"severity": "error", "msg": "Failed to parse property."},
    "KSVA-E002": {"severity": "error", "msg": "Property not found."},
    "KSVA-E003": {"severity": "error", "msg": "Unbalanced parentheses."},
    "KSVA-E004": {"severity": "error", "msg": "Top-level implication not found."},
}


def rule_message(code: str) -> str:
    return RULES.get(code, {}).get("msg", code)


def rule_severity(code: str) -> str:
    return RULES.get(code, {}).get("severity", "warning")
