PYTHON ?= $(shell if [ -x "$(HOME)/miniconda3/bin/python" ]; then echo "$(HOME)/miniconda3/bin/python"; else echo python3; fi)
PYTHONPATH := $(CURDIR)/src

.PHONY: all test unit-test smoke clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src

test: unit-test smoke

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kentry.cli decode --config examples/entry.yaml --input examples/fragments.jsonl --json >/tmp/kentry_decode.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kentry.cli explain --config examples/entry.yaml --json >/tmp/kentry_explain.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kentry.cli validate --config examples/entry.yaml --input examples/fragments.jsonl --json >/tmp/kentry_validate.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/kentry_decode.json >/dev/null
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/kentry_explain.json >/dev/null
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/kentry_validate.json >/dev/null
	printf '%s\n' '{"api_version":"kentry.v1","action":"decode","config_path":"examples/entry.yaml","input_path":"examples/fragments.jsonl"}' | PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kentry.cli --json - >/tmp/kentry_stdin.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/kentry_stdin.json >/dev/null
	printf '%s\n' '{"api_version":"kentry.v1","action":"explain","config_path":"examples/entry.yaml"}' | PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kentry.cli - | grep -q '^@kentry.explain.v1'

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
