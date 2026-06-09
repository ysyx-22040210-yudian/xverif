"""Router CLI."""

from __future__ import annotations

import argparse
from typing import List, Optional

from .router import Router


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-workers", type=int, default=64)
    parser.add_argument("--request-timeout-sec", type=float, default=30.0)
    args = parser.parse_args(argv)
    return Router(args.max_workers, args.request_timeout_sec).serve()


if __name__ == "__main__":
    raise SystemExit(main())

