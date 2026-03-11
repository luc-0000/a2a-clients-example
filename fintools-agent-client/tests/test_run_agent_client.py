import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_agent_client.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("run_agent_client", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RunAgentClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_normalize_mode_accepts_streaming(self):
        self.assertEqual(self.module.normalize_mode("streaming"), "streaming")

    def test_normalize_mode_accepts_polling(self):
        self.assertEqual(self.module.normalize_mode("polling"), "polling")

    def test_normalize_mode_rejects_old_internal_name(self):
        with self.assertRaises(SystemExit):
            self.module.normalize_mode("recoverable_polling")

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
        try:
            self.assertTrue(auto_created)
            self.assertTrue(Path(work_dir).name.startswith("fintools-agent-client-run-"))
        finally:
            Path(work_dir).rmdir()

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
                "persist_dir": None,
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
                 mock.patch.object(self.module, "find_python_runtime", return_value={"type": "venv", "detail": "current:/usr/bin/python3", "python": "/usr/bin/python3"}), \
                 mock.patch.object(self.module, "print_runtime_banner"), \
                 mock.patch.object(self.module, "prepare_runtime", return_value="/tmp/fake-python"), \
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
                        "persist_dir": None,
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
                self.assertEqual(called_cmd[1], "-u")


if __name__ == "__main__":
    unittest.main()
