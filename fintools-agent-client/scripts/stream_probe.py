#!/usr/bin/env python3
"""Minimal stdout streaming probe for host agents."""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path


SKILL_NAME = "fintools-agent-client"
DEFAULT_PARENT_DIR = Path("/tmp") / f"{SKILL_NAME}-runs"
PROBE_DIRNAME = "probe"
LOG_NAME = "stream_probe.log"


def parse_args():
    parser = argparse.ArgumentParser(description="Emit timed lines and mirror them into the skill probe directory.")
    parser.add_argument("--work-dir", help="Parent directory for skill runs and probe outputs.")
    parser.add_argument("--lines", type=int, default=10, help="Number of lines to emit.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between lines.")
    return parser.parse_args()


def ensure_parent_dir(raw_work_dir):
    if raw_work_dir:
        parent_dir = Path(raw_work_dir).expanduser().resolve()
    else:
        parent_dir = DEFAULT_PARENT_DIR
    parent_dir.mkdir(parents=True, exist_ok=True)
    return parent_dir


def ensure_probe_dir(parent_dir):
    probe_dir = Path(parent_dir) / PROBE_DIRNAME
    probe_dir.mkdir(parents=True, exist_ok=True)
    return probe_dir


def main():
    args = parse_args()
    parent_dir = ensure_parent_dir(args.work_dir)
    probe_dir = ensure_probe_dir(parent_dir)
    log_path = probe_dir / LOG_NAME

    print(f"Parent directory: {parent_dir}", flush=True)
    print(f"Probe directory: {probe_dir}", flush=True)
    print(f"Probe log: {log_path}", flush=True)

    with log_path.open("a", encoding="utf-8") as log_handle:
        for index in range(1, args.lines + 1):
            line = "[{timestamp}] stream_probe: [{current}/{total}] streaming check".format(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                current=index,
                total=args.lines,
            )
            print(line, flush=True)
            log_handle.write(line + "\n")
            log_handle.flush()
            if index < args.lines:
                time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
