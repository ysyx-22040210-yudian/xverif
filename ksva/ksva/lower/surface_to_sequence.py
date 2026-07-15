"""Surface IR → Sequence Graph IR lowering.

将 SurfaceIR 的 antecedent_raw / consequent_raw 解析为 SeqNode 列表。
"""

from __future__ import annotations

from ksva.ir.diagnostics import DiagnosticBag
from ksva.ir.surface import SurfaceIR
from ksva.ir.sequence import SeqNode, SeqNodeKind, SequenceIR

from ksva.parser.scanner import Scanner
from ksva.parser.sequence_parser import SequenceParser


def lower_surface_to_sequence(
    surface: SurfaceIR,
    diag: DiagnosticBag | None = None,
) -> SequenceIR:
    """将 SurfaceIR lowering 为 SequenceIR。

    步骤：
    1. 解析 antecedent_raw → SeqNode 列表
    2. 解析 consequent_raw → SeqNode 列表
    3. 合并：antecedent 的最后一个 node + implication 标记 + consequent nodes
    """
    if diag is None:
        diag = DiagnosticBag()

    all_nodes: list[SeqNode] = []

    # 1. 解析 antecedent
    if surface.antecedent_raw.strip():
        scanner = Scanner(surface.antecedent_raw, file="<antecedent>")
        seq_parser = SequenceParser(scanner, diag)
        ant_nodes = seq_parser.parse_sequence()
        all_nodes.extend(ant_nodes)

    # 2. 添加 implication 标记
    impl = surface.implication
    if impl == "|->":
        all_nodes.append(SeqNode(kind=SeqNodeKind.IMPLICATION))
    elif impl == "|=>":
        # |=> 等价于 |-> ##1
        all_nodes.append(SeqNode(kind=SeqNodeKind.IMPLICATION))
        all_nodes.append(SeqNode.delay_cycles(1))

    # 3. 解析 consequent
    if surface.consequent_raw.strip():
        scanner = Scanner(surface.consequent_raw, file="<consequent>")
        seq_parser = SequenceParser(scanner, diag)
        cons_nodes = seq_parser.parse_sequence()
        all_nodes.extend(cons_nodes)

    return SequenceIR(
        name=surface.name,
        nodes=all_nodes,
        captures=[],  # populated during sequence_to_timeline
        lowering_status=surface.lowering_status.value,
    )
