"""Shared pytest infrastructure for kdebug tests."""

from .artifacts import ArtifactWriter
from .assertions import InvariantError, assert_invariants
from .cli import CliRunner, RunResult
from .command import CommandRunner
from .manifests import ManifestError, TestManifest, load_manifest
from .normalize import NormalizeOptions, normalize_response
from .stdio_loop import StdioLoopRunner

__all__ = [
    "ArtifactWriter",
    "CliRunner",
    "CommandRunner",
    "InvariantError",
    "ManifestError",
    "NormalizeOptions",
    "RunResult",
    "StdioLoopRunner",
    "TestManifest",
    "assert_invariants",
    "load_manifest",
    "normalize_response",
]
