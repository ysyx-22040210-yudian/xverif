"""Evidence IR：预留给后续波形/反例解释使用。

Phase 1 仅占位定义，不做实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvidenceIR:
    """波形证据 IR — Phase 1 占位。"""

    schema_version: str = "ksva.evidence_ir.v1"
    property_name: str = ""
    # 后续扩展: signal_samples, counterexample, waveform_references 等
