PYTHON ?= python3
PYTHONPATH := $(CURDIR)

.PHONY: all test unit-test clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q xloc

test: unit-test

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

clean:
	find xloc tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find xloc tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
