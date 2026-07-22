#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kdebug_evidence import collect_case, validate_case_evidence, validate_suite

try:
    import jsonschema
except ImportError:  # The runtime validator itself has no third-party dependency.
    jsonschema = None


class KDebugEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fake = self.root / "fake_kdebug.py"
        self.fake.write_text(
            """import json
import pathlib
import sys

request = json.loads(pathlib.Path(sys.argv[-1]).read_text(encoding='utf-8'))
payload = {
    'api_version': 'kdebug.v1',
    'request_id': request['request_id'],
    'ok': True,
    'action': request['action'],
    'tool': {'name': 'kdebug', 'version': 'test-1.0'},
    'summary': {'signal': request.get('args', {}).get('signal', '')},
    'data': {'value': '1', 'source': 'real-tool-response'}
}
if request.get('args', {}).get('copy_fail_log'):
    payload['data']['observed_failure_tail'] = pathlib.Path('fail/run.log').read_text(encoding='utf-8')
print(json.dumps(payload))
""",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def make_case(self, number=1, copy_fail_log=False):
        case_id = f"case_{number:03d}"
        case = self.root / case_id
        (case / "fail").mkdir(parents=True)
        (case / "evidence" / "requests").mkdir(parents=True)
        (case / "inputs").mkdir(parents=True)
        (case / "fail" / "run.log").write_text(
            "FAIL " + "shared simulator failure text " * 30,
            encoding="utf-8",
        )
        (case / "inputs" / "waves.fsdb").write_bytes(b"FSDB-test-data\x00\x01")
        meta = {
            "suite": "test-suite",
            "case_id": case_id,
            "bug_domain": "rtl",
            "tool_evidence": {
                "required_for_with_kdebug": True,
                "plan": "evidence/kdebug_plan.json",
                "expected_files": ["kdebug_value.json"],
                "minimum_nonempty_files": 1,
            },
        }
        plan = {
            "schema_version": "kdebug-evidence-plan.v1",
            "case_id": case_id,
            "minimum_successful_invocations": 1,
            "minimum_diagnostic_invocations": 1,
            "max_fail_log_similarity": 0.8,
            "requests": [
                {
                    "id": "first_value",
                    "request": "evidence/requests/first_value.json",
                    "output": "kdebug_value.json",
                    "diagnostic": True,
                }
            ],
        }
        request = {
            "api_version": "kdebug.v1",
            "action": "value.at",
            "target": {"fsdb": "inputs/waves.fsdb"},
            "args": {"signal": "tb.dut.ready", "time": "10ns"},
        }
        if copy_fail_log:
            request["args"]["copy_fail_log"] = True
        self.write_json(case / "case_meta.json", meta)
        self.write_json(case / "evidence" / "kdebug_plan.json", plan)
        self.write_json(case / "evidence" / "requests" / "first_value.json", request)
        return case

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def write_manifest(cls, path, value):
        cls.write_json(path, value)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (path.parent / "manifest.sha256").write_text(
            f"{digest}  manifest.json\n",
            encoding="ascii",
        )

    def command(self):
        return [sys.executable, str(self.fake)]

    def test_collect_validate_and_reuse(self):
        case = self.make_case()
        first = collect_case(case, self.command())
        self.assertTrue(first["valid"], first["errors"])
        self.assertFalse(first["reused"])
        second = collect_case(case, self.command())
        self.assertTrue(second["valid"], second["errors"])
        self.assertTrue(second["reused"])
        manifest = json.loads((case / "evidence" / "with_kdebug" / "manifest.json").read_text())
        self.assertEqual(manifest["summary"]["successful_diagnostic_invocations"], 1)
        self.assertEqual(manifest["invocations"][0]["command_argv"][-2], "--json")

    def test_evidence_remains_valid_in_repair_workdir_copy(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        repair = self.root / "repair" / case.name
        repair.parent.mkdir()
        shutil.copytree(case, repair, copy_function=shutil.copy2)
        result = validate_case_evidence(repair)
        self.assertTrue(result["valid"], result["errors"])

    @unittest.skipIf(jsonschema is None, "jsonschema is not installed")
    def test_generated_manifest_matches_public_schema(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        manifest = json.loads(
            (case / "evidence" / "with_kdebug" / "manifest.json").read_text(encoding="utf-8")
        )
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "kdebug_evidence_manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(manifest)

    def test_tampered_response_is_rejected(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        response = case / "evidence" / "with_kdebug" / "kdebug_value.json"
        response.write_text(response.read_text(encoding="utf-8") + " ", encoding="utf-8")
        result = validate_case_evidence(case)
        self.assertFalse(result["valid"])
        self.assertTrue(any("sha256 mismatch" in error for error in result["errors"]))

    def test_response_cannot_diverge_from_raw_stdout_even_with_updated_hashes(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        evidence = case / "evidence" / "with_kdebug"
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        response_path = evidence / "kdebug_value.json"
        response = json.loads(response_path.read_text(encoding="utf-8"))
        response["data"]["value"] = "fabricated"
        self.write_json(response_path, response)
        record = manifest["invocations"][0]["response"]
        record["size"] = response_path.stat().st_size
        record["sha256"] = hashlib.sha256(response_path.read_bytes()).hexdigest()
        self.write_manifest(manifest_path, manifest)
        result = validate_case_evidence(case)
        self.assertFalse(result["valid"])
        self.assertTrue(any("differs from raw KDebug stdout" in error for error in result["errors"]))

    def test_canonical_request_cannot_diverge_from_case_request(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        evidence = case / "evidence" / "with_kdebug"
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        request_path = evidence / "_requests" / "first_value.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request["args"]["signal"] = "tb.dut.fabricated"
        self.write_json(request_path, request)
        record = manifest["invocations"][0]["request"]
        record["size"] = request_path.stat().st_size
        record["sha256"] = hashlib.sha256(request_path.read_bytes()).hexdigest()
        self.write_manifest(manifest_path, manifest)
        result = validate_case_evidence(case)
        self.assertFalse(result["valid"])
        self.assertTrue(any("canonical request differs" in error for error in result["errors"]))

    def test_malformed_manifest_fails_closed_instead_of_crashing(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        manifest_path = case / "evidence" / "with_kdebug" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["started_at_epoch_ns"] = "not-an-integer"
        self.write_manifest(manifest_path, manifest)
        result = validate_case_evidence(case)
        self.assertFalse(result["valid"])
        self.assertTrue(any("manifest validation error" in error for error in result["errors"]))

    def test_changed_input_is_rejected(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        with (case / "inputs" / "waves.fsdb").open("ab") as stream:
            stream.write(b"changed")
        result = validate_case_evidence(case)
        self.assertFalse(result["valid"])
        self.assertTrue(any("fingerprint mismatch" in error for error in result["errors"]))

    def test_fail_log_copy_is_rejected(self):
        case = self.make_case(copy_fail_log=True)
        result = collect_case(case, self.command())
        self.assertFalse(result["valid"])
        self.assertTrue(any("duplicates fail log" in error for error in result["errors"]))

    def test_suite_rejects_reused_collection_id(self):
        first_case = self.make_case(1)
        second_case = self.make_case(2)
        first = collect_case(first_case, self.command())
        second = collect_case(second_case, self.command())
        self.assertTrue(first["valid"], first["errors"])
        self.assertTrue(second["valid"], second["errors"])
        first_manifest = json.loads((first_case / "evidence" / "with_kdebug" / "manifest.json").read_text())
        second_manifest_path = second_case / "evidence" / "with_kdebug" / "manifest.json"
        second_manifest = json.loads(second_manifest_path.read_text())
        second_manifest["collection_id"] = first_manifest["collection_id"]
        self.write_json(second_manifest_path, second_manifest)
        digest = hashlib.sha256(second_manifest_path.read_bytes()).hexdigest()
        (second_manifest_path.parent / "manifest.sha256").write_text(
            f"{digest}  manifest.json\n",
            encoding="ascii",
        )
        result = validate_suite(self.root, ["case_001", "case_002"])
        self.assertFalse(result["valid"])
        self.assertTrue(any("reused across cases" in error for error in result["errors"]))

    def test_runner_rejects_invalid_evidence_before_api(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        response = case / "evidence" / "with_kdebug" / "kdebug_value.json"
        response.write_text(response.read_text(encoding="utf-8") + " ", encoding="utf-8")
        runner = Path(__file__).with_name("api_model_runner.py")
        proc = subprocess.run(
            [
                sys.executable,
                str(runner),
                "--model",
                "gpt-5.5",
                "--repair-dir",
                str(case),
                "--group",
                "with_kdebug",
                "--timeout",
                "10",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        metrics = json.loads(proc.stdout)
        self.assertEqual(metrics["final_status"], "TOOL_EVIDENCE_INVALID")
        self.assertFalse(metrics["tool_evidence_valid"])
        self.assertNotIn("API_KEY", proc.stderr)

    def test_runner_requires_every_declared_response_file(self):
        case = self.make_case()
        collected = collect_case(case, self.command())
        self.assertTrue(collected["valid"], collected["errors"])
        meta_path = case / "case_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["tool_evidence"]["expected_files"].append("missing_second_response.json")
        self.write_json(meta_path, meta)
        runner = Path(__file__).with_name("api_model_runner.py")
        proc = subprocess.run(
            [
                sys.executable,
                str(runner),
                "--model",
                "gpt-5.5",
                "--repair-dir",
                str(case),
                "--group",
                "with_kdebug",
                "--timeout",
                "10",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        metrics = json.loads(proc.stdout)
        self.assertEqual(metrics["final_status"], "TOOL_EVIDENCE_MISSING")
        self.assertFalse(metrics["tool_evidence_present"])
        self.assertNotIn("API_KEY", proc.stderr)


if __name__ == "__main__":
    unittest.main()
