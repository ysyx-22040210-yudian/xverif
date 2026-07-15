"""Path expand 单元测试。"""

from ksva.ir.expr import ExprIR, ExprKind
from ksva.ir.sequence import SeqNode, SeqNodeKind
from ksva.lower.path_expand import expand_paths


def test_no_expand_fixed_delay():
    """固定延迟 ##3 不应展开。"""
    nodes = [
        SeqNode.delay_cycles(3),
        SeqNode.signal_match(ExprIR(kind=ExprKind.IDENTIFIER, raw="ack")),
    ]
    paths = expand_paths(nodes)
    assert len(paths) == 1, f"Fixed delay should produce 1 path, got {len(paths)}"


def test_expand_range_delay_with_suffix():
    """##[1:3] ack ##1 done → 3 条路径。"""
    nodes = [
        SeqNode.delay_cycles(1, 3),
        SeqNode.signal_match(ExprIR(kind=ExprKind.IDENTIFIER, raw="ack")),
        SeqNode.delay_cycles(1),
        SeqNode.signal_match(ExprIR(kind=ExprKind.IDENTIFIER, raw="done")),
    ]
    paths = expand_paths(nodes)
    assert len(paths) == 3, f"Range delay with suffix should produce 3 paths, got {len(paths)}"

    # 路径 0: ##1 ack ##1 done
    assert paths[0][0].delay.min_cycles == 1
    assert paths[0][0].delay.max_cycles is None

    # 路径 1: ##2 ack ##1 done
    assert paths[1][0].delay.min_cycles == 2

    # 路径 2: ##3 ack ##1 done
    assert paths[2][0].delay.min_cycles == 3


def test_no_expand_range_without_suffix():
    """##[1:4] ack → 不展开，保持单路径。"""
    nodes = [
        SeqNode.delay_cycles(1, 4),
        SeqNode.signal_match(ExprIR(kind=ExprKind.IDENTIFIER, raw="ack")),
    ]
    paths = expand_paths(nodes)
    assert len(paths) == 1, f"Range delay without suffix should be 1 path, got {len(paths)}"


def test_max_paths_truncation():
    """超过 max_paths 应截断。"""
    nodes = [
        SeqNode.delay_cycles(1, 20),
        SeqNode.signal_match(ExprIR(kind=ExprKind.IDENTIFIER, raw="x")),
        SeqNode.delay_cycles(1, 10),
        SeqNode.signal_match(ExprIR(kind=ExprKind.IDENTIFIER, raw="y")),
    ]
    paths = expand_paths(nodes, max_paths=5)
    assert len(paths) <= 5, f"Paths should be truncated to 5, got {len(paths)}"


def test_empty_sequence():
    """空 sequence 返回单一空路径。"""
    paths = expand_paths([])
    assert len(paths) == 1
    assert paths[0] == []
