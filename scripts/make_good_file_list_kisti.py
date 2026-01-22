#!/usr/bin/env python3
"""
Simple wrapper (put in ./scripts/)

Usage:
  python3 ./scripts/run_make_good_file_list_crab.py /T2_KR_KISTI/store/user/...

It converts:
  /T2_KR_KISTI/store/...  ->  /store/...
and runs:
  ./scripts/make_good_file_list_crab.py --server cms-t2-se01.sdfarm.kr:1094 /store/...

You can override the server:
  python3 ./scripts/run_make_good_file_list_crab.py --server host:port /T2_KR_KISTI/store/...
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_SERVER = "cms-t2-se01.sdfarm.kr:1094"
SITE_PREFIX = "/T2_KR_KISTI"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Either /T2_KR_KISTI/... or /store/... or root://...")
    ap.add_argument("--server", default=DEFAULT_SERVER, help="XRootD server host:port")
    args, rest = ap.parse_known_args()

    p = args.path

    # If user gave /T2_KR_KISTI/..., strip it to /...
    if p.startswith(SITE_PREFIX + "/") or p == SITE_PREFIX:
        p = p[len(SITE_PREFIX):]
        if p == "":
            p = "/"
        if not p.startswith("/"):
            p = "/" + p

    scripts_dir = Path(__file__).resolve().parent
    underlying = scripts_dir / "make_good_file_list_crab.py"

    cmd = [sys.executable, str(underlying)]

    # Only pass --server if the input is NOT already a root:// URL
    if not p.startswith("root://"):
        cmd += ["--server", args.server]

    cmd += rest + [p]

    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

