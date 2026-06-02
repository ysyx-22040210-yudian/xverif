PYTHON ?= $(shell if [ -x "$(HOME)/miniconda3/bin/python" ]; then echo "$(HOME)/miniconda3/bin/python"; else echo python3; fi)
PYTHONPATH := $(CURDIR)/src

.PHONY: all test unit-test smoke clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src

test: unit-test smoke

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m xentry.cli decode --config examples/entry.yaml --input examples/fragments.jsonl --json >/tmp/xentry_decode.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m xentry.cli explain --config examples/entry.yaml --json >/tmp/xentry_explain.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m xentry.cli validate --config examples/entry.yaml --input examples/fragments.jsonl --json >/tmp/xentry_validate.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/xentry_decode.json >/dev/null
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/xentry_explain.json >/dev/null
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/xentry_validate.json >/dev/null
	printf '%s\n' '{"api_version":"xentry.v1","action":"decode","config_path":"examples/entry.yaml","input_path":"examples/fragments.jsonl"}' | PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m xentry.cli - >/tmp/xentry_stdin.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/xentry_stdin.json >/dev/null

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
