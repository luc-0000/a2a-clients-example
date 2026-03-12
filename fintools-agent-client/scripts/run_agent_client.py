#!/usr/bin/env python3
"""Bootstrap and run the local Fintools agent client in an isolated workspace."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime


SKILL_NAME = "fintools-agent-client"
DEFAULT_PARENT_DIRNAME = "{0}-runs".format(SKILL_NAME)
RUN_PREFIX = "{0}-run-".format(SKILL_NAME)
SUMMARY_NAME = "summary.json"
LOG_NAME = "run.log"
SHARED_ENVS_DIRNAME = "shared-envs"
PROBE_DIRNAME = "probe"
LOCK_POLL_INTERVAL = 0.2
LOCK_TIMEOUT_SECONDS = 300
TOKEN_FILENAME = ".fintools_access_token"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
AGENTS_CLIENT_DIR = SKILL_ROOT / "agents_client"
REQUIREMENTS_FILE = SKILL_ROOT / "requirements.txt"


def fail(message, exit_code=2):
    print("ERROR: {0}".format(message), file=sys.stderr)
    raise SystemExit(exit_code)


def announce_status(message):
    print("[status] {0}".format(message), flush=True)


def announce_result(message):
    print("[result] {0}".format(message), flush=True)


def validate_skill_layout():
    missing = []
    if not AGENTS_CLIENT_DIR.is_dir():
        missing.append("agents_client/")
    if not REQUIREMENTS_FILE.is_file():
        missing.append("requirements.txt")
    if missing:
        fail(
            "The skill is incomplete. Missing required bundled files under {0}: {1}".format(
                SKILL_ROOT, ", ".join(missing)
            )
        )


validate_skill_layout()


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
    parser.add_argument("--task-id")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--_in-env", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_work-dir-auto-created", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()

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


def token_file_path(parent_dir):
    return Path(parent_dir) / TOKEN_FILENAME


def load_cached_access_token(parent_dir):
    token_path = token_file_path(parent_dir)
    if token_path.is_file():
        token = token_path.read_text(encoding="utf-8").strip()
        if token:
            return token
    return None


def save_access_token(parent_dir, token):
    token_path = token_file_path(parent_dir)
    token_path.write_text(token.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass


def resolve_access_token(args, parent_dir=None):
    token = args.access_token or os.environ.get("FINTOOLS_ACCESS_TOKEN")
    if not token and parent_dir is not None:
        token = load_cached_access_token(parent_dir)
    if not token:
        fail("Missing FINTOOLS_ACCESS_TOKEN. Pass --access-token or set the environment variable.")
    if parent_dir is not None and token:
        save_access_token(parent_dir, token)
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


def safe_name_fragment(value):
    allowed = []
    for char in str(value or "").strip().lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {"-", "_"}:
            allowed.append("-")
    fragment = "".join(allowed).strip("-")
    return fragment or "unknown"


def create_run_dir(parent_dir, agent_type, stock_code, mode):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = "{0}{1}-{2}-{3}-{4}".format(
        RUN_PREFIX,
        safe_name_fragment(agent_type),
        safe_name_fragment(stock_code),
        safe_name_fragment(mode),
        timestamp,
    )
    parent_path = Path(parent_dir)
    run_dir = parent_path / base_name
    if not run_dir.exists():
        run_dir.mkdir(parents=False, exist_ok=False)
        return run_dir

    for sequence in range(2, 1000):
        candidate = parent_path / "{0}-{1:03d}".format(base_name, sequence)
        if not candidate.exists():
            candidate.mkdir(parents=False, exist_ok=False)
            return candidate

    fail("Could not allocate a unique run directory under {0}".format(parent_dir))


def shared_envs_dir(parent_dir):
    path = Path(parent_dir) / SHARED_ENVS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_work_dir(raw_work_dir):
    if raw_work_dir:
        parent_dir = Path(raw_work_dir).expanduser().resolve()
        parent_dir.mkdir(parents=True, exist_ok=True)
        return parent_dir, False

    tmp_root = Path("/tmp")
    if tmp_root.exists() and tmp_root.is_dir() and os.access(tmp_root, os.W_OK | os.X_OK):
        parent_dir = tmp_root / DEFAULT_PARENT_DIRNAME
        parent_dir.mkdir(parents=True, exist_ok=True)
        return parent_dir, True

    parent_dir = Path(tempfile.gettempdir()) / DEFAULT_PARENT_DIRNAME
    parent_dir.mkdir(parents=True, exist_ok=True)
    return parent_dir, True


def run_command(cmd, env=None, cwd=None):
    subprocess.run(cmd, check=True, env=env, cwd=str(cwd) if cwd else None)


def requirements_fingerprint():
    requirements_bytes = REQUIREMENTS_FILE.read_bytes()
    return hashlib.sha256(requirements_bytes).hexdigest()[:12]


def runtime_version_tag(runtime):
    if runtime["type"] == "venv":
        version = version_for(runtime["python"])
        if not version:
            fail("Unable to determine Python version for shared venv runtime.")
        return "py{0}{1}".format(version[0], version[1])
    return "py310"


def acquire_lock(lock_path):
    start = time.time()
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return
        except FileExistsError:
            if time.time() - start > LOCK_TIMEOUT_SECONDS:
                fail("Timed out waiting for environment lock: {0}".format(lock_path))
            time.sleep(LOCK_POLL_INTERVAL)


def release_lock(lock_path):
    try:
        Path(lock_path).unlink()
    except FileNotFoundError:
        pass


def shared_runtime_dir(parent_dir, runtime):
    shared_root = shared_envs_dir(parent_dir)
    fingerprint = requirements_fingerprint()
    version_tag = runtime_version_tag(runtime)
    env_prefix = "venv" if runtime["type"] == "venv" else "conda"
    return shared_root / "{0}-{1}-{2}".format(env_prefix, version_tag, fingerprint)


def runtime_ready_marker(env_dir):
    return Path(env_dir) / ".ready"


def log_file_path(work_dir):
    return Path(work_dir) / LOG_NAME


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self):
        for stream in self.streams:
            stream.flush()

    def isatty(self):
        return False


def prepare_runtime(runtime, parent_dir):
    base_env = os.environ.copy()
    base_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env_dir = shared_runtime_dir(parent_dir, runtime)
    lock_path = "{0}.lock".format(env_dir)
    announce_status("正在准备共享运行环境: {0}".format(env_dir))
    acquire_lock(lock_path)
    try:
        if runtime["type"] == "venv":
            python_path = env_dir / "bin" / "python"
            ready_marker = runtime_ready_marker(env_dir)
            if not python_path.exists():
                announce_status("正在创建共享 venv 环境")
                run_command([runtime["python"], "-m", "venv", str(env_dir)], env=base_env)
            if not ready_marker.exists():
                announce_status("正在安装依赖到共享 venv 环境")
                run_command([str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], env=base_env)
                ready_marker.write_text("ok\n")
            else:
                announce_status("检测到已就绪的共享 venv 环境，直接复用")
            return str(python_path), str(env_dir)

        python_path = env_dir / "bin" / "python"
        ready_marker = runtime_ready_marker(env_dir)
        if not python_path.exists():
            announce_status("正在创建共享 conda 环境")
            run_command([runtime["python"], "create", "-y", "-p", str(env_dir), "python=3.10"], env=base_env)
        if not ready_marker.exists():
            announce_status("正在安装依赖到共享 conda 环境")
            run_command([str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], env=base_env)
            ready_marker.write_text("ok\n")
        else:
            announce_status("检测到已就绪的共享 conda 环境，直接复用")
        return str(python_path), str(env_dir)
    finally:
        release_lock(lock_path)


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


def maybe_cleanup(work_dir, cleanup_requested):
    if not cleanup_requested:
        return False
    shutil.rmtree(work_dir, ignore_errors=True)
    print("Cleaned up run directory: {0}".format(work_dir))
    return True


def write_summary(work_dir, payload):
    summary_path = Path(work_dir) / SUMMARY_NAME
    summary_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n")
    return summary_path


def print_runtime_banner(parent_dir, work_dir, parent_auto_created, runtime, runtime_env_dir):
    source = "auto-created parent directory" if parent_auto_created else "user-provided parent directory"
    print("Parent directory: {0}".format(parent_dir))
    print("Parent directory source: {0}".format(source))
    print("Run directory: {0}".format(work_dir))
    print("Runtime type: {0}".format(runtime["type"]))
    print("Runtime detail: {0}".format(runtime["detail"]))
    print("Shared runtime directory: {0}".format(runtime_env_dir))


async def run_inside_env(args):
    announce_status("正在读取访问令牌")
    token = resolve_access_token(args)
    work_dir = Path(args.work_dir).resolve()
    parent_auto_created = args._work_dir_auto_created
    reports_dir = work_dir / "downloaded_reports"
    announce_status("正在准备当前 run 目录")
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_log = log_file_path(work_dir)

    os.chdir(str(work_dir))
    if str(SKILL_ROOT) not in sys.path:
        sys.path.insert(0, str(SKILL_ROOT))

    error = None
    success = False
    report_path = None
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with run_log.open("a", encoding="utf-8") as log_handle:
        tee_stdout = TeeStream(original_stdout, log_handle)
        tee_stderr = TeeStream(original_stderr, log_handle)
        sys.stdout = tee_stdout
        sys.stderr = tee_stderr
        try:
            announce_status("当前日志文件: {0}".format(run_log))
            if args.mode == "streaming" and args.agent_type == "deep_research":
                announce_status("正在启动 Deep Research Agent（streaming）")
                success, report_path = await run_streaming_deep_research(args.stock_code, args.agent_url, token, str(reports_dir))
            elif args.mode == "streaming" and args.agent_type == "trading":
                announce_status("正在启动 Trading Agent（streaming）")
                success, report_path = await run_streaming_trading(args.stock_code, args.agent_url, token, str(reports_dir))
            elif args.mode == "polling" and args.agent_type == "trading":
                announce_status("正在启动 Trading Agent（polling）")
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
        finally:
            tee_stdout.flush()
            tee_stderr.flush()
            sys.stdout = original_stdout
            sys.stderr = original_stderr

    summary = {
        "agent_type": args.agent_type,
        "mode": args.mode,
        "stock_code": args.stock_code,
        "agent_url": args.agent_url,
        "runtime_type": os.environ.get("FINTOOLS_RUNTIME_TYPE", "unknown"),
        "runtime_detail": os.environ.get("FINTOOLS_RUNTIME_DETAIL", "unknown"),
        "runtime_env_dir": os.environ.get("FINTOOLS_RUNTIME_ENV_DIR", "unknown"),
        "work_dir": str(work_dir),
        "parent_dir_source": "auto-created" if parent_auto_created else "user-provided",
        "run_dir": str(work_dir),
        "log_path": str(run_log),
        "report_path": report_path,
        "success": bool(success),
        "cleanup_requested": bool(args.cleanup),
        "cleanup_performed": False,
        "error": error,
    }
    summary_path = write_summary(work_dir, summary)
    cleanup_planned = bool(args.cleanup)
    summary["cleanup_performed"] = cleanup_planned
    announce_status("正在写入 summary.json")
    summary_path = write_summary(work_dir, summary)
    cleanup_performed = maybe_cleanup(work_dir, args.cleanup)

    if not cleanup_performed:
        summary["cleanup_performed"] = False
        write_summary(work_dir, summary)
        announce_result("Summary written to: {0}".format(summary_path))

    announce_result("Report path: {0}".format(report_path or "none"))
    announce_result("Run log: {0}".format(run_log))
    announce_result("Run directory: {0}".format(work_dir))
    announce_result("Run success: {0}".format("yes" if success else "no"))
    if error:
        announce_result("Run error: {0}".format(error))

    if success:
        return 0
    return 1


def main():
    announce_status("正在解析运行参数")
    args = parse_args()
    ensure_required(args)
    args.mode = normalize_mode(args.mode)

    if args._in_env:
        return asyncio.run(run_inside_env(args))

    announce_status("正在准备主目录")
    parent_dir, parent_auto_created = ensure_work_dir(args.work_dir)
    announce_status("正在读取或缓存访问令牌")
    token = resolve_access_token(args, parent_dir)
    announce_status("正在创建本次 run 目录")
    work_dir = create_run_dir(parent_dir, args.agent_type, args.stock_code, args.mode)
    announce_status("正在检查 Python 运行环境")
    runtime = find_python_runtime()
    env_python, runtime_env_dir = prepare_runtime(runtime, parent_dir)
    print_runtime_banner(parent_dir, work_dir, parent_auto_created, runtime, runtime_env_dir)

    child_env = os.environ.copy()
    child_env["FINTOOLS_ACCESS_TOKEN"] = token
    child_env["FINTOOLS_RUNTIME_TYPE"] = runtime["type"]
    child_env["FINTOOLS_RUNTIME_DETAIL"] = runtime["detail"]
    child_env["FINTOOLS_RUNTIME_ENV_DIR"] = runtime_env_dir
    child_env["PYTHONUNBUFFERED"] = "1"

    child_args = [env_python, "-u", str(Path(__file__).resolve())] + build_reexec_args(args, work_dir, parent_auto_created)
    announce_status("正在启动子进程执行 agent client")
    completed = subprocess.run(child_args, env=child_env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
