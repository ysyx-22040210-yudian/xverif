.PHONY: test audit-tcl-npi-only

PYTHON ?= python3

audit-tcl-npi-only:
	@if grep -RInE 'py[n]pi|npi[s]ys|share/NPI/py[t]hon|NPI/py[t]hon' kcov tcl_engine tests 2>/dev/null; then \
		echo "ERROR: kcov direct coverage NPI access must stay in tcl_engine/kcov_npi.tcl." >&2; \
		exit 1; \
	fi

test: audit-tcl-npi-only
	PYTHONPATH=. $(PYTHON) -m pytest tests
