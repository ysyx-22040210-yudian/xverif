"""bsub -I command construction and startup."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .protocol import JsonlProcess


@dataclass
class BsubOptions:
    queue: Optional[str] = None
    resource: Optional[str] = None
    job_name: Optional[str] = None

    def extra_args(self) -> List[str]:
        """Extra flags to pass to bsub before the command."""
        extras: List[str] = []
        if self.job_name:
            extras.extend(["-J", self.job_name])
        if self.queue:
            extras.extend(["-q", self.queue])
        if self.resource:
            extras.extend(["-R", self.resource])
        return extras


class BsubRunner:
    def __init__(self, bsub_cmd: Optional[str] = None) -> None:
        self.bsub_cmd = bsub_cmd or os.environ.get("XDEBUG_LSF_BSUB", "bsub")

    def build(self, command: Iterable[str], opts: Optional[BsubOptions] = None) -> List[str]:
        opts = opts or BsubOptions()
        base = shlex.split(self.bsub_cmd)
        if "-I" not in base:
            base.append("-I")
        base.extend(opts.extra_args())
        base.extend(list(command))
        return base

    def start(self, command: Iterable[str], opts: Optional[BsubOptions] = None) -> JsonlProcess:
        return JsonlProcess.start(self.build(command, opts))

