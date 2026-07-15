#!/usr/bin/env python3
"""Check ActionSpec files against runtime kdebug actions output."""

import json
import subprocess
import sys
from pathlib import Path


def fail(message):
    raise SystemExit("ERROR: " + message)


def load_json(path):
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        fail("%s: cannot parse JSON-subset YAML: %s" % (path, exc))


def load_specs(root):
    specs = {}
    files = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")) + sorted(root.glob("*.json"))
    if not files:
        fail("no spec files found under %s" % root)
    for path in files:
        doc = load_json(path)
        actions = doc.get("actions") if isinstance(doc, dict) else doc
        if not isinstance(actions, list):
            fail("%s: expected top-level actions array" % path)
        for spec in actions:
            if not isinstance(spec, dict):
                fail("%s: action spec must be an object" % path)
            name = spec.get("name")
            if not isinstance(name, str) or not name:
                fail("%s: action spec missing name" % path)
            if name in specs:
                fail("duplicate action spec: %s" % name)
            specs[name] = spec
    return specs


def require_file(path, base):
    full = base / path
    if not full.exists():
        fail("referenced file does not exist: %s" % path)


def check_spec_shape(specs, kdebug_root):
    valid_status = {"experimental", "stable", "deprecated", "removed"}
    valid_requires = {"none", "design", "waveform", "combined", "any", "session"}
    for name, spec in sorted(specs.items()):
        for key in ("category", "status", "requires", "handler_kind"):
            if not isinstance(spec.get(key), str) or not spec.get(key):
                fail("%s: missing string field %s" % (name, key))
        if spec["status"] not in valid_status:
            fail("%s: invalid status %s" % (name, spec["status"]))
        if spec["requires"] not in valid_requires:
            fail("%s: invalid requires %s" % (name, spec["requires"]))
        if spec["status"] != "removed":
            schemas = spec.get("schemas", {})
            examples = spec.get("examples", {})
            for field in ("request", "response"):
                ref = schemas.get(field)
                if not isinstance(ref, str) or not ref:
                    fail("%s: action missing %s schema" % (name, field))
                if ref in ("schemas/v1/kdebug.request.schema.json", "schemas/v1/kdebug.response.schema.json"):
                    fail("%s: action must not use generic %s schema" % (name, field))
                expected = "schemas/v1/actions/%s.%s.schema.json" % (name, field)
                if ref != expected:
                    fail("%s: %s schema must be %s, got %s" % (name, field, expected, ref))
                require_file(ref, kdebug_root)
                refs = examples.get(field)
                if not isinstance(refs, list) or not refs:
                    fail("%s: action missing %s example" % (name, field))
                for example in refs:
                    require_file(example, kdebug_root)


def load_runtime_actions(exe):
    request = b'{"api_version":"kdebug.v1","action":"actions"}\n'
    try:
        raw = subprocess.check_output([str(exe), "--json"], input=request)
    except Exception as exc:
        fail("failed to run runtime actions output via %s: %s" % (exe, exc))
    try:
        doc = json.loads(raw)
    except Exception as exc:
        fail("runtime actions output is not JSON: %s" % exc)
    if not doc.get("ok"):
        fail("runtime actions output returned ok=false")
    return doc


def check_runtime(specs, runtime):
    implemented = set(runtime["data"].get("implemented", []))
    removed = set(runtime["data"].get("removed", []))
    spec_implemented = {name for name, spec in specs.items() if spec["status"] != "removed"}
    spec_removed = {name for name, spec in specs.items() if spec["status"] == "removed"}
    if implemented != spec_implemented:
        fail("implemented mismatch: missing=%s extra=%s" %
             (sorted(spec_implemented - implemented), sorted(implemented - spec_implemented)))
    if removed != spec_removed:
        fail("removed mismatch: missing=%s extra=%s" %
             (sorted(spec_removed - removed), sorted(removed - spec_removed)))
    descriptors = {item["name"]: item for item in runtime["data"].get("actions", [])}
    for name in sorted(spec_implemented):
        if name not in descriptors:
            fail("%s: missing runtime descriptor" % name)
        desc = descriptors[name]
        spec = specs[name]
        for field, runtime_field in (("category", "category"), ("status", "status"), ("requires", "requires")):
            if spec[field] != desc.get(runtime_field):
                fail("%s: %s mismatch spec=%s runtime=%s" %
                     (name, field, spec[field], desc.get(runtime_field)))
        schemas = spec.get("schemas", {})
        if schemas.get("request") != desc.get("request_schema"):
            fail("%s: request_schema mismatch spec=%s runtime=%s" %
                 (name, schemas.get("request"), desc.get("request_schema")))
        if schemas.get("response") != desc.get("response_schema"):
            fail("%s: response_schema mismatch spec=%s runtime=%s" %
                 (name, schemas.get("response"), desc.get("response_schema")))
        examples = spec.get("examples", {})
        if examples.get("request") != desc.get("request_examples"):
            fail("%s: request_examples mismatch spec=%s runtime=%s" %
                 (name, examples.get("request"), desc.get("request_examples")))
        runtime_response_examples = desc.get("response_examples")
        spec_response_examples = examples.get("response")
        if spec_response_examples and not set(spec_response_examples).issubset(set(runtime_response_examples or [])):
            fail("%s: response_examples spec must be subset of runtime spec=%s runtime=%s" %
                 (name, spec_response_examples, runtime_response_examples))


def main(argv):
    kdebug_root = Path(__file__).resolve().parents[1]
    specs_root = Path(argv[1]) if len(argv) > 1 else kdebug_root / "specs" / "actions"
    exe = Path(argv[2]) if len(argv) > 2 else kdebug_root / "kdebug"
    specs = load_specs(specs_root)
    check_spec_shape(specs, kdebug_root)
    runtime = load_runtime_actions(exe)
    check_runtime(specs, runtime)
    print("validated %d action specs against runtime actions" % len(specs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
