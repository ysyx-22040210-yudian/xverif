"""Obligation Timeline IR：面向人类解释和 Agent 消费的最终 IR。

对齐 spec 第十一章：
- TriggerIR, CaptureIR, ObligationIR, WindowIR, MatchPathIR, FailureConditionIR, TimelineIR
- ObligationKind Enum 用于类型安全
- disable 显式表达为 ObligationIR
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from .common import LoweringStatus, SourceSpan
from .diagnostics import DiagnosticIR
from .expr import ExprIR, SignalRef
from .surface import ClockIR

# Phase 1 兼容别名
ClockRefIR = ClockIR


# ── 枚举 ──

@enum.unique
class ObligationKind(enum.Enum):
    """Obligation 类型。对齐 spec 11.2。"""

    POINT = "point"  # 固定周期检查
    EVENTUALLY = "eventually"  # 窗口内至少发生一次
    HOLD = "hold"  # 窗口内保持
    STABLE = "stable"  # $stable
    ROSE = "rose"  # $rose
    FELL = "fell"  # $fell
    COMPARE_PAST = "compare_past"  # $past 比较
    SEQUENCE_PATH = "sequence_path"  # path-based sequence obligation


# ── 核心 IR ──

@dataclass
class CaptureIR:
    """local variable capture。对齐 spec 11.1。"""

    var: str = ""
    value_expr: str = ""
    relative_cycle: int = 0
    meaning: str = ""


@dataclass
class TriggerIR:
    """触发条件。对齐 spec 11.1。"""

    cycle: int = 0
    expr: str = ""
    captures: list[CaptureIR] = field(default_factory=list)


@dataclass(frozen=True)
class WindowIR:
    """时间窗口：[start, end]，相对 trigger 偏移。对齐 spec 11.1。"""

    start: int = 0
    end: int = 0
    unbounded: bool = False
    description: str = ""

    # Phase 1 兼容属性
    @property
    def min_cycle(self) -> int:
        return self.start

    @property
    def max_cycle(self) -> int | None:
        return self.end if not self.unbounded else None


@dataclass(frozen=True)
class ObligationIR:
    """单个 obligation。对齐 spec 11.1。

    kind: ObligationKind Enum 确保类型安全。
    signals_to_query: 标准化信号查询接口，方便 Evidence IR 对接。
    """

    id: str = ""
    kind: ObligationKind = ObligationKind.POINT
    expr: str = ""  # spec 用 str，同时保留 ExprIR 引用
    expr_ir: ExprIR | None = None

    has_cycle: bool = False
    cycle: int = 0

    has_window: bool = False
    window: WindowIR | None = None

    depends_on_captures: list[str] = field(default_factory=list)
    requirement: str = ""
    signals_to_query: list[SignalRef] = field(default_factory=list)
    failure_condition: str | None = None
    description: str = ""
    cycle_offset: int = 0  # Phase 1 兼容


@dataclass(frozen=True)
class MatchPathIR:
    """展开后的匹配路径。对齐 spec 11.1。"""

    id: str = ""
    captures: list[CaptureIR] = field(default_factory=list)
    obligations: tuple[ObligationIR, ...] = ()
    pass_condition: str = ""
    failure_condition: str = ""
    trigger_condition: str = ""  # Phase 1 兼容
    is_partial: bool = False
    description: str = ""


@dataclass(frozen=True)
class FailureConditionIR:
    """obligation 失败条件。"""

    obligation_id: str = ""
    condition: str = ""


@dataclass(frozen=True)
class SemanticNoteIR:
    """面向用户的高级语法语义摘要。"""

    kind: str = ""
    expr: str = ""
    text: str = ""


@dataclass
class TimelineIR:
    """Obligation Timeline IR — 最终输出 IR。对齐 spec 11.1。"""

    schema_version: str = "ksva.timeline_ir.v1"

    property_name: str = ""  # spec 用 "property"，但 Python @property 冲突
    kind: str = "assert"  # assert / assume / cover

    clock: ClockIR = field(default_factory=ClockIR)
    disable_expr: str = ""

    # 触发
    trigger: TriggerIR = field(default_factory=TriggerIR)

    # obligations（扁平列表）
    obligations: list[ObligationIR] = field(default_factory=list)

    # 展开路径
    match_paths: list[MatchPathIR] = field(default_factory=list)

    # failure
    failure_conditions: list[FailureConditionIR] = field(default_factory=list)

    # 高级 sequence / sampled function 的用户语义摘要
    semantic_notes: list[SemanticNoteIR] = field(default_factory=list)

    # vacuity
    vacuity_checks: list[str] = field(default_factory=list)

    # lowering
    lowering_status: LoweringStatus = LoweringStatus.EXACT
    diagnostics: list[DiagnosticIR] = field(default_factory=list)

    # ── Phase 1 兼容属性 ──

    @property
    def trigger_expr(self) -> str:
        return self.trigger.expr

    @trigger_expr.setter
    def trigger_expr(self, value: str) -> None:
        self.trigger.expr = value

    @property
    def trigger_captures(self) -> list:
        return [{"var": c.var, "expr": c.value_expr, "is_update": False}
                for c in self.trigger.captures]

    @property
    def paths(self) -> list[MatchPathIR]:
        """Phase 1 兼容：paths == match_paths."""
        return list(self.match_paths)

    @property
    def disable_obligation(self) -> ObligationIR | None:
        """Phase 1 兼容：从 vacuity_checks 或 diagnostics 重建。"""
        return None  # 由 lowering 层显式设置

    def add_disable_obligation(self, obl: ObligationIR) -> None:
        """添加 disable obligation。"""
        self._disable_obl = obl

    @property
    def _compat_disable_obl(self) -> ObligationIR | None:
        return getattr(self, '_disable_obl', None)


# Phase 1 兼容别名
PathIR = MatchPathIR
