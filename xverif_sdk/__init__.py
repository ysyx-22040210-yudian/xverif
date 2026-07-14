"""Public Python SDK for composing xverif tools into verification workflows."""

from .clients import XcovClient, XdebugClient
from .errors import (ProtocolError, ToolInvocationError, ToolResponseError,
                     XverifSdkError)
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
    "XcovClient",
    "XdebugClient",
    "XverifSdkError",
    "analyze_coverage_convergence",
    "analyze_wave_window",
    "resolve_tool",
    "trace_module_connections",
]

__version__ = "0.1.0"
