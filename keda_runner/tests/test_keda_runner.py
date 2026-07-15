"""Unit tests for keda-runner."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent dir to path to import keda_runner
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from keda_runner import (build_argv, generate_init_script, load_env0,
                          parse_options, validate_value)


class TestLoadEnv0(unittest.TestCase):
    def test_basic(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"PATH=/bin\0HOME=/home\0SHELL=bash\0")
            path = f.name
        try:
            env = load_env0(path)
            self.assertEqual(env["PATH"], "/bin")
            self.assertEqual(env["HOME"], "/home")
            self.assertEqual(env["SHELL"], "bash")
        finally:
            os.unlink(path)

    def test_empty(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"")
            path = f.name
        try:
            env = load_env0(path)
            self.assertEqual(env, {})
        finally:
            os.unlink(path)

    def test_trailing_null(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"KEY=val\0\0")
            path = f.name
        try:
            env = load_env0(path)
            self.assertEqual(env, {"KEY": "val"})
        finally:
            os.unlink(path)


class TestGenerateInitScript(unittest.TestCase):
    def _cfg(self, shell="bash", **kw):
        return {
            "shell": shell,
            "workdir": "/tmp/work",
            "init_steps": ["source /tmp/setup.sh"],
            "checks": ["make"],
            "env_snapshot": ".keda_runner/env/env.env0",
            **kw,
        }

    def test_bash_set_e(self):
        script = generate_init_script(self._cfg("bash"))
        self.assertIn("set -e", script)

    def test_zsh_set_e(self):
        script = generate_init_script(self._cfg("zsh"))
        self.assertIn("set -e", script)

    def test_tcsh_status_check(self):
        script = generate_init_script(self._cfg("tcsh"))
        self.assertIn("if ($status != 0) exit 10", script)

    def test_auto_cd_workdir(self):
        script = generate_init_script(self._cfg("tcsh", workdir="/proj/nic/work"))
        self.assertIn("cd /proj/nic/work", script)

    def test_checks_fail_fast(self):
        script = generate_init_script(self._cfg("tcsh"))
        # "which make" should be followed by a status check
        self.assertIn("which make", script)

    def test_no_cd_in_init_steps_needed(self):
        """Runner auto-inserts cd workdir; user should NOT put it in init_steps."""
        script = generate_init_script(self._cfg("tcsh"))
        # The auto cd should be after init_steps, before checks
        cd_pos = script.find("cd /tmp/work")
        check_pos = script.find("which make")
        self.assertGreater(cd_pos, 0)
        self.assertLess(cd_pos, check_pos)


class TestBuildArgv(unittest.TestCase):
    def _action(self, **kw):
        return {
            "command": "make",
            "fixed_args": ["-j8"],
            "target": {"required": False},
            "options": {},
            **kw,
        }

    def test_make_var(self):
        cfg = self._action(options={
            "TEST": {"emit": "make_var", "pattern": "^[A-Za-z0-9_./+-]+$"},
        })
        argv = build_argv(cfg, None, {"TEST": "smoke"})
        self.assertIn("TEST=smoke", argv)

    def test_separate(self):
        cfg = self._action(options={
            "filelist": {"emit": "separate", "key": "-f", "pattern": "^.*$"},
        })
        argv = build_argv(cfg, None, {"filelist": "files.f"})
        idx = argv.index("-f")
        self.assertEqual(argv[idx + 1], "files.f")

    def test_flag_truthy(self):
        cfg = self._action(options={
            "debug": {"emit": "flag", "key": "-debug_access+all"},
        })
        argv = build_argv(cfg, None, {"debug": "1"})
        self.assertIn("-debug_access+all", argv)

    def test_flag_false_skipped(self):
        cfg = self._action(options={
            "debug": {"emit": "flag", "key": "-debug_access+all"},
        })
        argv = build_argv(cfg, None, {"debug": "0"})
        self.assertNotIn("-debug_access+all", argv)

    def test_equals(self):
        cfg = self._action(options={
            "top": {"emit": "equals", "key": "--top"},
        })
        argv = build_argv(cfg, None, {"top": "tb_top"})
        self.assertIn("--top=tb_top", argv)

    def test_positional(self):
        cfg = self._action(options={
            "input": {"emit": "positional"},
        })
        argv = build_argv(cfg, None, {"input": "input.fsdb"})
        self.assertIn("input.fsdb", argv)

    def test_reject_bad_target(self):
        cfg = self._action(target={
            "required": True, "allowed": ["sim", "compile"],
        })
        with self.assertRaises(ValueError):
            build_argv(cfg, "clean", {})

    def test_reject_bad_option_value_values(self):
        cfg = self._action(options={
            "WAVES": {"emit": "make_var", "values": ["0", "1"]},
        })
        with self.assertRaises(ValueError):
            build_argv(cfg, None, {"WAVES": "2"})

    def test_reject_bad_option_value_pattern(self):
        cfg = self._action(options={
            "SEED": {"emit": "make_var", "pattern": "^[0-9]+$"},
        })
        with self.assertRaises(ValueError):
            build_argv(cfg, None, {"SEED": "abc"})

    def test_required_option_missing(self):
        cfg = self._action(options={
            "TEST": {"emit": "make_var", "required": True},
        })
        with self.assertRaises(ValueError) as ctx:
            build_argv(cfg, None, {})
        self.assertIn("required option missing: TEST", str(ctx.exception))

    def test_required_option_present(self):
        cfg = self._action(options={
            "TEST": {"emit": "make_var", "required": True},
        })
        argv = build_argv(cfg, None, {"TEST": "smoke"})
        self.assertIn("TEST=smoke", argv)


class TestParseOptions(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_options(["A=1", "B=2"]), {"A": "1", "B": "2"})

    def test_empty(self):
        self.assertEqual(parse_options([]), {})
        self.assertEqual(parse_options(None), {})

    def test_no_equals(self):
        with self.assertRaises(ValueError):
            parse_options(["badformat"])


class TestValidateValue(unittest.TestCase):
    def test_values_ok(self):
        validate_value("WAVES", "1", {"values": ["0", "1"]})

    def test_values_fail(self):
        with self.assertRaises(ValueError):
            validate_value("WAVES", "2", {"values": ["0", "1"]})

    def test_pattern_ok(self):
        validate_value("SEED", "123", {"pattern": "^[0-9]+$"})

    def test_pattern_fail(self):
        with self.assertRaises(ValueError):
            validate_value("SEED", "abc", {"pattern": "^[0-9]+$"})


if __name__ == "__main__":
    unittest.main()
