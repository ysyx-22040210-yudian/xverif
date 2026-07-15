"""Public Python SDK for composing kverif tools into verification workflows."""

from .clients import KcovClient, KdebugClient
from .errors import (ProtocolError, ToolInvocationError, ToolResponseError,
                     KverifSdkError)
from .transport import CallbackTransport, CliTransport, StdioTransport, resolve_tool
from .workflows import (CoverageRun, analyze_coverage_convergence,
                        analyze_wave_window, trace_module_connections)

__all__ = [
    "CallbackTransport",
    "CliTransport",
    "CoverageRun",
    "ProtocolError",
    "StdioTransport",
    "ToolInvocationError",
    "ToolResponseError",
    "KcovClient",
    "KdebugClient",
    "KverifSdkError",
    "analyze_coverage_convergence",
    "analyze_wave_window",
    "resolve_tool",
    "trace_module_connections",
]

__version__ = "0.1.0"
