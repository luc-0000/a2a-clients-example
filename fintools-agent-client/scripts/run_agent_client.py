#!/usr/bin/env python3
"""Bootstrap and run the local Fintools agent client in an isolated workspace."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "fintools-agent-client"
TEMP_PREFIX = "{0}-run-".format(SKILL_NAME)
SUMMARY_NAME = "summary.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Fintools agent client with an isolated workspace.")
    parser.add_argument("--agent-type", choices=["deep_research", "trading"])
    parser.add_argument(
        "--mode",
        help="Execution mode: streaming or polling.",
    )
    parser.add_argument("--stock-code")
    parser.add_argument("--agent-url")
    parser.add_argument("--access-token")
    parser.add_argument("--work-dir")
    parser.add_argument("--persist-dir")
    parser.add_argument("--task-id")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--_in-env", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_work-dir-auto-created", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def fail(message, exit_code=2):
    print("ERROR: {0}".format(message), file=sys.stderr)
    raise SystemExit(exit_code)


def ensure_required(args):
    missing = []
    if not args.agent_type:
        missing.append("--agent-type")
    if not args.mode:
        missing.append("--mode")
    if not args.stock_code:
        missing.append("--stock-code")
    if not args.agent_url:
        missing.append("--agent-url")
    if missing:
        fail("Missing required arguments: {0}".format(", ".join(missing)))


def normalize_mode(mode):
    mapping = {
        "streaming": "streaming",
        "polling": "polling",
    }
    normalized = mapping.get((mode or "").strip().lower())
    if not normalized:
        fail("Unsupported --mode value: {0}. Use streaming or polling.".format(mode))
    return normalized


def resolve_access_token(args):
    token = args.access_token or os.environ.get("FINTOOLS_ACCESS_TOKEN")
    if not token:
        fail("Missing FINTOOLS_ACCESS_TOKEN. Pass --access-token or set the environment variable.")
    return token


def version_for(executable):
    try:
        output = subprocess.check_output(
            [str(executable), "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None

    parts = output.split(".")
    if len(parts) < 2:
        return None
    try:
        return tuple(int(part) for part in parts[:3])
    except ValueError:
        return None


def find_python_runtime():
    current = Path(sys.executable)
    current_version = version_for(current)
    if current_version and current_version >= (3, 10, 0):
        return {
            "type": "venv",
            "detail": "current:{0}".format(current),
            "python": str(current),
        }

    seen = set()
    candidates = ["python3.13", "python3.12", "python3.11", "python3.10", "python3"]
    for name in candidates:
        path = shutil.which(name)
        if not path or path in seen:
            continue
        seen.add(path)
        candidate_version = version_for(path)
        if candidate_version and candidate_version >= (3, 10, 0):
            return {
                "type": "venv",
                "detail": "{0}:{1}".format(name, path),
                "python": path,
            }

    conda = shutil.which("conda")
    if conda:
        return {
            "type": "conda",
            "detail": "conda:{0}".format(conda),
            "python": conda,
        }

    fail("No compatible Python 3.10+ interpreter or conda executable was found.")


def ensure_work_dir(raw_work_dir):
    if raw_work_dir:
        work_dir = Path(raw_work_dir).expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir, False

    work_dir = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
    return work_dir, True


def run_command(cmd, env=None, cwd=None):
    subprocess.run(cmd, check=True, env=env, cwd=str(cwd) if cwd else None)


def prepare_runtime(runtime, work_dir):
    base_env = os.environ.copy()
    base_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    if runtime["type"] == "venv":
        venv_dir = work_dir / ".venv"
        python_path = venv_dir / "bin" / "python"
        if not python_path.exists():
            run_command([runtime["python"], "-m", "venv", str(venv_dir)], env=base_env)
        run_command([str(python_path), "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")], env=base_env)
        return str(python_path)

    env_dir = work_dir / "conda-env"
    python_path = env_dir / "bin" / "python"
    if not python_path.exists():
        run_command([runtime["python"], "create", "-y", "-p", str(env_dir), "python=3.10"], env=base_env)
    run_command([str(python_path), "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")], env=base_env)
    return str(python_path)


def build_reexec_args(args, work_dir, auto_created):
    argv = [
        "--agent-type", args.agent_type,
        "--mode", args.mode,
        "--stock-code", args.stock_code,
        "--agent-url", args.agent_url,
        "--work-dir", str(work_dir),
        "--_in-env",
    ]
    if auto_created:
        argv.append("--_work-dir-auto-created")
    if args.access_token:
        argv.extend(["--access-token", args.access_token])
    if args.persist_dir:
        argv.extend(["--persist-dir", args.persist_dir])
    if args.task_id:
        argv.extend(["--task-id", args.task_id])
    if args.cleanup:
        argv.append("--cleanup")
    return argv


async def run_streaming_deep_research(stock_code, agent_url, token, output_dir):
    from agents_client.streaming.dr_agent_client_stream import run_dr_agent
    from agents_client.utils import ReportDownloader

    success = await run_dr_agent(stock_code, agent_url, token)
    downloader = ReportDownloader(agent_url, token)
    report_path = await downloader.download_zip(output_dir=output_dir)
    return success, report_path


async def run_streaming_trading(stock_code, agent_url, token, output_dir):
    from agents_client.streaming.trading_agent_client_stream import run_trading_agent
    from agents_client.utils import ReportDownloader, normalize_agent_base_url

    success = await run_trading_agent(stock_code, agent_url, token)
    downloader = ReportDownloader(
        normalize_agent_base_url(agent_url),
        token,
        reports_path="reports",
        reports_zip_path="reports/zip",
    )
    report_path = await downloader.download_zip(output_dir=output_dir)
    return success, report_path


async def run_polling_trading(stock_code, agent_url, token, task_id):
    from agents_client.db_polling.trading_agent_client_db import main as run_main

    result = await run_main(agent_url, stock_code, token, task_id=task_id)
    return result


def persist_outputs(work_dir, persist_dir):
    if not persist_dir:
        return None

    target = Path(persist_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    summary_src = work_dir / SUMMARY_NAME
    if summary_src.exists():
        shutil.copy2(summary_src, target / SUMMARY_NAME)

    reports_src = work_dir / "downloaded_reports"
    if reports_src.exists():
        reports_dst = target / "downloaded_reports"
        if reports_dst.exists():
            shutil.rmtree(reports_dst)
        shutil.copytree(reports_src, reports_dst)

    return str(target)


def maybe_cleanup(work_dir, auto_created, cleanup_requested, persisted):
    if not cleanup_requested:
        return False
    if not auto_created:
        print("Cleanup skipped: work_dir was user-provided.")
        return False
    if not persisted:
        print("Cleanup skipped: outputs were not persisted.")
        return False
    shutil.rmtree(work_dir, ignore_errors=True)
    print("Cleaned up auto-created work directory: {0}".format(work_dir))
    return True


def write_summary(work_dir, payload):
    summary_path = Path(work_dir) / SUMMARY_NAME
    summary_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")
    return summary_path


def print_runtime_banner(work_dir, auto_created, runtime):
    source = "auto-created temporary directory" if auto_created else "user-provided directory"
    print("Working directory: {0}".format(work_dir))
    print("Working directory source: {0}".format(source))
    print("Runtime type: {0}".format(runtime["type"]))
    print("Runtime detail: {0}".format(runtime["detail"]))


async def run_inside_env(args):
    token = resolve_access_token(args)
    work_dir = Path(args.work_dir).resolve()
    auto_created = args._work_dir_auto_created
    reports_dir = work_dir / "downloaded_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    os.chdir(str(work_dir))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    error = None
    success = False
    report_path = None

    try:
        if args.mode == "streaming" and args.agent_type == "deep_research":
            success, report_path = await run_streaming_deep_research(args.stock_code, args.agent_url, token, str(reports_dir))
        elif args.mode == "streaming" and args.agent_type == "trading":
            success, report_path = await run_streaming_trading(args.stock_code, args.agent_url, token, str(reports_dir))
        elif args.mode == "polling" and args.agent_type == "trading":
            result = await run_polling_trading(args.stock_code, args.agent_url, token, args.task_id)
            success = result.get("status") == "completed"
            report_path = result.get("downloaded_file")
            error = result.get("error")
        else:
            fail("The repository does not implement polling for deep_research.")
    except SystemExit:
        raise
    except Exception as exc:
        error = str(exc)

    summary = {
        "agent_type": args.agent_type,
        "mode": args.mode,
        "stock_code": args.stock_code,
        "agent_url": args.agent_url,
        "runtime_type": os.environ.get("FINTOOLS_RUNTIME_TYPE", "unknown"),
        "runtime_detail": os.environ.get("FINTOOLS_RUNTIME_DETAIL", "unknown"),
        "work_dir": str(work_dir),
        "work_dir_source": "auto-created" if auto_created else "user-provided",
        "persist_dir": args.persist_dir,
        "report_path": report_path,
        "success": bool(success),
        "cleanup_requested": bool(args.cleanup),
        "cleanup_performed": False,
        "error": error,
    }
    summary["persist_dir"] = str(Path(args.persist_dir).expanduser().resolve()) if args.persist_dir else None
    summary_path = write_summary(work_dir, summary)
    persisted = persist_outputs(work_dir, args.persist_dir)
    summary["persist_dir"] = persisted or summary["persist_dir"]
    cleanup_planned = bool(args.cleanup and auto_created and persisted)
    summary["cleanup_performed"] = cleanup_planned
    summary_path = write_summary(work_dir, summary)
    if persisted:
        persisted = persist_outputs(work_dir, args.persist_dir)
    cleanup_performed = maybe_cleanup(work_dir, auto_created, args.cleanup, persisted)

    if not cleanup_performed:
        write_summary(work_dir, summary)
        print("Summary written to: {0}".format(summary_path))

    print("Report path: {0}".format(report_path or "none"))
    print("Persisted outputs: {0}".format(persisted or "not requested"))
    print("Run success: {0}".format("yes" if success else "no"))
    if error:
        print("Run error: {0}".format(error))

    if success:
        return 0
    return 1


def main():
    args = parse_args()
    ensure_required(args)
    args.mode = normalize_mode(args.mode)

    if args._in_env:
        return asyncio.run(run_inside_env(args))

    token = resolve_access_token(args)
    work_dir, auto_created = ensure_work_dir(args.work_dir)
    runtime = find_python_runtime()
    print_runtime_banner(work_dir, auto_created, runtime)

    env_python = prepare_runtime(runtime, work_dir)
    child_env = os.environ.copy()
    child_env["FINTOOLS_ACCESS_TOKEN"] = token
    child_env["FINTOOLS_RUNTIME_TYPE"] = runtime["type"]
    child_env["FINTOOLS_RUNTIME_DETAIL"] = runtime["detail"]
    child_env["PYTHONUNBUFFERED"] = "1"

    child_args = [env_python, "-u", str(Path(__file__).resolve())] + build_reexec_args(args, work_dir, auto_created)
    completed = subprocess.run(child_args, env=child_env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
