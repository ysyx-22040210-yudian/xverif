PYTHON ?= $(shell if [ -x "$(HOME)/miniconda3/bin/python" ]; then echo "$(HOME)/miniconda3/bin/python"; else echo python3; fi)
PYTHONPATH := $(CURDIR)

.PHONY: all test unit-test smoke clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q kberif

test: unit-test smoke

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests

smoke:
	tmp=$$(mktemp -d /tmp/kberif_smoke.XXXXXX); \
	cd "$$tmp"; \
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kberif config init --kind bt >/tmp/kberif_config_init.log; \
	test -f "$$tmp/kberif/kind.toml"; \
	rm -rf "$$tmp"

clean:
	find kberif tests -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
