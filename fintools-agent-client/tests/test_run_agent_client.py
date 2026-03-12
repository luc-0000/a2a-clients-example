from datetime import datetime
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_agent_client.py"
)
STREAM_PROBE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "stream_probe.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("run_agent_client", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_stream_probe_module():
    spec = importlib.util.spec_from_file_location("stream_probe", STREAM_PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RunAgentClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.stream_probe = load_stream_probe_module()

    def test_normalize_mode_accepts_streaming(self):
        self.assertEqual(self.module.normalize_mode("streaming"), "streaming")

    def test_normalize_mode_accepts_polling(self):
        self.assertEqual(self.module.normalize_mode("polling"), "polling")

    def test_normalize_mode_rejects_old_internal_name(self):
        with self.assertRaises(SystemExit):
            self.module.normalize_mode("recoverable_polling")

    def test_skill_root_contains_bundled_runtime_files(self):
        self.assertTrue(self.module.AGENTS_CLIENT_DIR.is_dir())
        self.assertTrue(self.module.REQUIREMENTS_FILE.is_file())

    def test_validate_skill_layout_fails_cleanly_when_bundled_files_missing(self):
        with mock.patch.object(self.module, "AGENTS_CLIENT_DIR", Path("/tmp/missing-agents-client")), \
             mock.patch.object(self.module, "REQUIREMENTS_FILE", Path("/tmp/missing-requirements.txt")):
            with self.assertRaises(SystemExit):
                self.module.validate_skill_layout()

    def test_standalone_skill_copy_imports_without_parent_repo(self):
        skill_root = MODULE_PATH.parents[1]
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-standalone-") as tmpdir:
            copied_root = Path(tmpdir) / "fintools-agent-client"
            shutil.copytree(skill_root, copied_root)
            copied_module_path = copied_root / "scripts" / "run_agent_client.py"
            spec = importlib.util.spec_from_file_location("standalone_run_agent_client", copied_module_path)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)

            self.assertEqual(module.SKILL_ROOT.resolve(), copied_root.resolve())
            self.assertTrue(module.AGENTS_CLIENT_DIR.is_dir())
            self.assertTrue(module.REQUIREMENTS_FILE.is_file())

    def test_token_file_path(self):
        self.assertEqual(
            self.module.token_file_path("/tmp/example-parent"),
            Path("/tmp/example-parent/.fintools_access_token"),
        )

    def test_save_and_load_cached_access_token(self):
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-token-") as tmpdir:
            self.module.save_access_token(tmpdir, "secret-token")
            self.assertEqual(self.module.load_cached_access_token(tmpdir), "secret-token")

    def test_resolve_access_token_uses_cache(self):
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-token-") as tmpdir:
            self.module.save_access_token(tmpdir, "cached-token")
            args = type("Args", (), {"access_token": None})()
            with mock.patch.dict(self.module.os.environ, {}, clear=True):
                self.assertEqual(self.module.resolve_access_token(args, tmpdir), "cached-token")

    def test_ensure_required_rejects_missing_agent_url(self):
        args = type(
            "Args",
            (),
            {
                "agent_type": "trading",
                "mode": "streaming",
                "stock_code": "600519",
                "agent_url": None,
            },
        )()
        with self.assertRaises(SystemExit):
            self.module.ensure_required(args)

    def test_auto_work_dir_prefix_contains_skill_name(self):
        work_dir, auto_created = self.module.ensure_work_dir(None)
        self.assertTrue(auto_created)
        self.assertEqual(Path(work_dir).name, "fintools-agent-client-runs")

    def test_auto_work_dir_prefers_tmp_when_available(self):
        with mock.patch.object(self.module.os, "access", return_value=True):
            work_dir, auto_created = self.module.ensure_work_dir(None)
        self.assertTrue(auto_created)
        self.assertEqual(Path(work_dir).parent, Path("/tmp"))
        self.assertEqual(Path(work_dir).name, "fintools-agent-client-runs")

    def test_stream_probe_uses_same_default_parent_dir(self):
        parent_dir = self.stream_probe.ensure_parent_dir(None)
        self.assertEqual(parent_dir, Path("/tmp/fintools-agent-client-runs"))

    def test_stream_probe_keeps_output_under_probe_directory(self):
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-parent-") as tmpdir:
            probe_dir = self.stream_probe.ensure_probe_dir(tmpdir)
            self.assertEqual(probe_dir, Path(tmpdir) / "probe")

    def test_safe_name_fragment(self):
        self.assertEqual(self.module.safe_name_fragment("Deep Research"), "deepresearch")
        self.assertEqual(self.module.safe_name_fragment("600519"), "600519")
        self.assertEqual(self.module.safe_name_fragment("streaming"), "streaming")

    def test_create_run_dir_under_parent(self):
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-parent-") as tmpdir:
            run_dir = self.module.create_run_dir(tmpdir, "trading", "600519", "streaming")
            self.assertEqual(Path(run_dir).parent, Path(tmpdir))
            self.assertRegex(
                Path(run_dir).name,
                r"^run-trading-600519-streaming-\d{8}-\d{6}$",
            )

    def test_create_run_dir_adds_sequence_when_timestamp_collides(self):
        fixed_now = datetime(2026, 3, 12, 12, 0, 0)
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-parent-") as tmpdir, \
             mock.patch.object(self.module, "datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.strftime = datetime.strftime
            first_run = self.module.create_run_dir(tmpdir, "trading", "600519", "streaming")
            second_run = self.module.create_run_dir(tmpdir, "trading", "600519", "streaming")

            self.assertEqual(Path(first_run).name, "run-trading-600519-streaming-20260312-120000")
            self.assertEqual(Path(second_run).name, "run-trading-600519-streaming-20260312-120000-002")

    def test_shared_runtime_dir_for_venv(self):
        runtime = {"type": "venv", "detail": "current:{0}".format(sys.executable), "python": sys.executable}
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-parent-") as tmpdir:
            env_dir = self.module.shared_runtime_dir(tmpdir, runtime)
            self.assertEqual(Path(env_dir).parent.name, "shared-envs")
            self.assertTrue(Path(env_dir).name.startswith("venv-py"))

    def test_shared_runtime_dir_for_conda(self):
        runtime = {"type": "conda", "detail": "conda:/usr/bin/conda", "python": "/usr/bin/conda"}
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-parent-") as tmpdir:
            env_dir = self.module.shared_runtime_dir(tmpdir, runtime)
            self.assertEqual(Path(env_dir).parent.name, "shared-envs")
            self.assertTrue(Path(env_dir).name.startswith("conda-py310-"))

    def test_runtime_ready_marker_path(self):
        marker = self.module.runtime_ready_marker("/tmp/example-env")
        self.assertEqual(marker, Path("/tmp/example-env/.ready"))

    def test_log_file_path(self):
        self.assertEqual(
            self.module.log_file_path("/tmp/example-run"),
            Path("/tmp/example-run/run.log"),
        )

    def test_build_reexec_args_preserves_polling_mode(self):
        args = type(
            "Args",
            (),
            {
                "agent_type": "trading",
                "mode": "polling",
                "stock_code": "600519",
                "agent_url": "http://example.com/a2a/",
                "access_token": None,
                "task_id": None,
                "cleanup": False,
            },
        )()
        argv = self.module.build_reexec_args(args, Path("/tmp/work"), auto_created=True)
        self.assertIn("polling", argv)
        self.assertNotIn("recoverable_polling", argv)

    def test_main_uses_unbuffered_child_process(self):
        with tempfile.TemporaryDirectory(prefix="fintools-agent-client-test-") as tmpdir:
            with mock.patch.object(self.module, "parse_args") as mock_parse_args, \
                 mock.patch.object(self.module, "resolve_access_token", return_value="token"), \
                 mock.patch.object(self.module, "ensure_work_dir", return_value=(Path(tmpdir), True)), \
                 mock.patch.object(self.module, "create_run_dir", return_value=Path(tmpdir) / "run-trading-600519-streaming-20260312-120000"), \
                 mock.patch.object(self.module, "find_python_runtime", return_value={"type": "venv", "detail": "current:/usr/bin/python3", "python": "/usr/bin/python3"}), \
                 mock.patch.object(self.module, "print_runtime_banner"), \
                 mock.patch.object(self.module, "prepare_runtime", return_value=("/tmp/fake-python", "/tmp/fintools-agent-client-runs/shared-envs/venv-py311-deadbeef")), \
                 mock.patch.object(self.module.subprocess, "run") as mock_subprocess_run:
                mock_parse_args.return_value = type(
                    "Args",
                    (),
                    {
                        "agent_type": "trading",
                        "mode": "streaming",
                        "stock_code": "600519",
                        "agent_url": "http://example.com/a2a/",
                        "access_token": None,
                        "work_dir": None,
                        "task_id": None,
                        "cleanup": False,
                        "_in_env": False,
                        "_work_dir_auto_created": False,
                    },
                )()
                mock_subprocess_run.return_value = type("Completed", (), {"returncode": 0})()

                result = self.module.main()

                self.assertEqual(result, 0)
                called_args = mock_subprocess_run.call_args.kwargs["env"]
                called_cmd = mock_subprocess_run.call_args.args[0]
                self.assertEqual(called_args["PYTHONUNBUFFERED"], "1")
                self.assertEqual(called_args["FINTOOLS_RUNTIME_ENV_DIR"], "/tmp/fintools-agent-client-runs/shared-envs/venv-py311-deadbeef")
                self.assertEqual(called_cmd[1], "-u")


if __name__ == "__main__":
    unittest.main()
