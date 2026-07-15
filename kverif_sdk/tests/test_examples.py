from __future__ import annotations

from kverif_sdk.examples.coverage_convergence import build_parser


def test_coverage_example_explicit_metrics_do_not_include_defaults():
    args = build_parser().parse_args([
        "--run", "nightly=/results/nightly/simv.vdb",
        "--metrics", "line,toggle",
    ])
    assert args.metrics == ["line,toggle"]


def test_coverage_example_uses_workflow_defaults_when_metrics_are_omitted():
    args = build_parser().parse_args([
        "--run", "nightly=/results/nightly/simv.vdb",
    ])
    assert args.metrics is None
