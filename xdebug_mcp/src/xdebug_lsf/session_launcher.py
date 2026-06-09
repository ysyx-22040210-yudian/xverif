"""Launch and track xdebug TCP session endpoints."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, Optional

from .bsub import BsubOptions, BsubRunner
from .protocol import JsonlProcess


Json = Dict[str, object]


@dataclass
class SessionInfo:
    alias: str
    session_id: str
    job_name: Optional[str]
    host: str
    port: int
    token: str
    pid: Optional[int]
    fsdb: str
    daidir: Optional[str]
    state: str = "alive"
    process: Optional[JsonlProcess] = None
    job_id: Optional[str] = None

    def public_json(self) -> Json:
        out: Json = {
            "alias": self.alias,
            "session_id": self.session_id,
            "job_name": self.job_name,
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "fsdb": self.fsdb,
            "daidir": self.daidir,
            "state": self.state,
        }
        if self.job_id:
            out["job_id"] = self.job_id
        return out


class SessionLauncher:
    def __init__(self, bsub: BsubRunner, startup_timeout_sec: float = 30.0, fake: bool = False) -> None:
        self.bsub = bsub
        self.startup_timeout_sec = startup_timeout_sec
        self.fake = fake

    def open(
        self,
        alias: str,
        fsdb: str,
        daidir: Optional[str] = None,
        queue: Optional[str] = None,
        resource: Optional[str] = None,
        session_id: Optional[str] = None,
        job_prefix: Optional[str] = None,
    ) -> SessionInfo:
        sid = session_id or alias
        prefix = job_prefix or "xdebug"
        job_name = f"{prefix}_sess_{alias}"
        bind_addr = os.environ.get("XDEBUG_LSF_SESSION_BIND", "0.0.0.0:0")
        cmd = [
            sys.executable,
            "-m",
            "xdebug_lsf.session_server",
            "--tcp",
            bind_addr,
            "--session-id",
            sid,
            "--fsdb",
            fsdb,
        ]
        if daidir:
            cmd.extend(["--daidir", daidir])
        if self.fake:
            cmd.append("--fake")
        proc = self.bsub.start(cmd, BsubOptions(
            queue=queue, resource=resource, job_name=job_name))
        ready = proc.wait_ready("xdebug-session-tcp", self.startup_timeout_sec)
        return SessionInfo(
            alias=alias,
            session_id=str(ready["session_id"]),
            job_name=job_name,
            host=str(ready["host"]),
            port=int(ready["port"]),
            token=str(ready["token"]),
            pid=int(ready.get("pid") or 0),
            fsdb=fsdb,
            daidir=daidir,
            process=proc,
            job_id=proc.job_id,
        )
