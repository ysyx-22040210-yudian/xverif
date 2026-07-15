PYTHON ?= $(shell if [ -x "$(HOME)/miniconda3/bin/python" ]; then echo "$(HOME)/miniconda3/bin/python"; else echo python3; fi)
PYTHONPATH := $(CURDIR)/src

.PHONY: all test unit-test smoke clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q src

test: unit-test smoke

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kbit.cli conv "8'shff" --json >/tmp/kbit_conv.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m kbit.cli eval "data[15:8] == 8'hbe" --var "data=32'hdead_beef" --json >/tmp/kbit_eval.json
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/kbit_conv.json >/dev/null
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m json.tool /tmp/kbit_eval.json >/dev/null

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf build dist *.egg-info
