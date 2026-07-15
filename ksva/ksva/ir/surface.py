"""Surface IR：property 的外壳信息。

对齐 spec 第八章。
保存 clock、disable、antecedent/consequent 原文、implication 类型。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from .common import LoweringStatus, SourceSpan
from .diagnostics import DiagnosticIR


@dataclass
class ClockIR:
    """时钟信息。"""

    edge: str = "unknown"  # posedge / negedge / edge / unknown
    signal: str = ""
    supported: bool = True


@dataclass
class LocalVarIR:
    """local variable 声明。"""

    name: str
    var_type: str = ""  # logic [31:0] etc.
    scope: str = "property"  # property / sequence
    lifetime: str = "per_attempt"
    span: SourceSpan = field(default_factory=SourceSpan)


@enum.unique
class AssertionKind(str, enum.Enum):
    ASSERT = "assert"
    ASSUME = "assume"
    COVER = "cover"
    PROPERTY = "property"


@dataclass
class SurfaceIR:
    """Property 的外壳信息。对齐 spec 第八章。"""

    schema_version: str = "ksva.surface_ir.v1"

    name: str = ""
    label: str = ""
    kind: str = "assert"  # assert / assume / cover / property

    raw_text: str = ""

    clock: ClockIR = field(default_factory=ClockIR)
    disable_expr: str = ""

    local_vars: list[LocalVarIR] = field(default_factory=list)

    antecedent_raw: str = ""
    implication: str = ""  # |-> / |=>
    consequent_raw: str = ""

    is_named_property: bool = False
    is_inline_property: bool = False

    span: SourceSpan = field(default_factory=SourceSpan)
    diagnostics: list[DiagnosticIR] = field(default_factory=list)

    lowering_status: LoweringStatus = LoweringStatus.EXACT
