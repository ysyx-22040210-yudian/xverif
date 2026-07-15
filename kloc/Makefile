PYTHON ?= python3
PYTHONPATH := $(CURDIR)

.PHONY: all test unit-test vim-test clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q kloc

test: unit-test vim-test

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

vim-test:
	tmp=$$(mktemp -d /tmp/kloc_vim_test.XXXXXX); \
	KLOC_VIM_PLUGIN="$(CURDIR)/vim/plugin/kloc.vim" \
	KLOC_VIM_TMP="$$tmp" \
	vim -Nu NONE -n -es -S vim/checks/kloc_smoke.vim; \
	rc=$$?; \
	rm -rf "$$tmp"; \
	exit $$rc

clean:
	find kloc tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find kloc tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
