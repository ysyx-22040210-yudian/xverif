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


class BsubRunner:
    def __init__(self, bsub_cmd: Optional[str] = None) -> None:
        self.bsub_cmd = bsub_cmd or os.environ.get("XDEBUG_LSF_BSUB", "bsub")

    def build(self, command: Iterable[str], opts: Optional[BsubOptions] = None) -> List[str]:
        opts = opts or BsubOptions()
        base = shlex.split(self.bsub_cmd)
        if "-I" not in base:
            base.append("-I")
        if opts.queue:
            base.extend(["-q", opts.queue])
        if opts.resource:
            base.extend(["-R", opts.resource])
        base.extend(list(command))
        return base

    def start(self, command: Iterable[str], opts: Optional[BsubOptions] = None) -> JsonlProcess:
        return JsonlProcess.start(self.build(command, opts))

