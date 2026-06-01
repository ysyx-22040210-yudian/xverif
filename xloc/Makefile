PYTHON ?= python3
PYTHONPATH := $(CURDIR)

.PHONY: all test unit-test vim-test clean

all:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m compileall -q xloc

test: unit-test vim-test

unit-test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -v

vim-test:
	tmp=$$(mktemp -d /tmp/xloc_vim_test.XXXXXX); \
	XLOC_VIM_PLUGIN="$(CURDIR)/vim/plugin/xloc.vim" \
	XLOC_VIM_TMP="$$tmp" \
	vim -Nu NONE -n -es -S vim/checks/xloc_smoke.vim; \
	rc=$$?; \
	rm -rf "$$tmp"; \
	exit $$rc

clean:
	find xloc tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find xloc tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
