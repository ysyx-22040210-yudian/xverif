TOP ?= ../../..

include $(TOP)/mk/common_flags.mk

PYTHON ?= python3
KDEBUG ?= $(TOP)/tools/kdebug

BUILD := build

.PHONY: all clean chain_test probe \
        p0_0_fixture p0_1_fixture p0_2_fixture p0_3_fixture \
        p0_5_fixture p0_6_fixture

all:
	@echo "active_trace_chain now uses the Tcl-backed kdebug CLI; no C++ NPI harness is built."

chain_test:
	mkdir -p $(BUILD)
	printf '%s\n' '#!/usr/bin/env bash' \
		'set -euo pipefail' \
		'python3 "$$(dirname "$$0")/../run_kdebug_chain.py" "$$@"' > $(BUILD)/$@
	chmod +x $(BUILD)/$@

clean:
	rm -rf $(BUILD)
	for d in p0_composability/p0_*; do make -C $$d clean 2>/dev/null || true; done

# ── fixture targets ──
p0_0_fixture:
	make -C p0_composability/p0_0_assign_chain fixture

p0_1_fixture:
	make -C p0_composability/p0_1_flop_boundary fixture

p0_2_fixture:
	make -C p0_composability/p0_2_module_boundary fixture

p0_3_fixture:
	make -C p0_composability/p0_3_generate_for fixture

p0_4_fixture:
	make -C ../../testdata/combined/interface_port_root fixture

p0_5_fixture:
	make -C p0_composability/p0_5_mux_branch fixture

p0_6_fixture:
	make -C p0_composability/p0_6_procedural_for fixture

all_fixtures: p0_0_fixture p0_1_fixture p0_2_fixture p0_3_fixture p0_4_fixture p0_5_fixture p0_6_fixture

# ── convenience: build + run one case ──
# usage: make run_p0_0
run_p0_0: chain_test p0_0_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_0 \
		p0_composability/p0_0_assign_chain/out/simv.daidir \
		p0_composability/p0_0_assign_chain/out/waves.fsdb \
		top.out 10ns $(BUILD)/p0_0

run_p0_1: chain_test p0_1_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_1 \
		p0_composability/p0_1_flop_boundary/out/simv.daidir \
		p0_composability/p0_1_flop_boundary/out/waves.fsdb \
		top.out 17ns $(BUILD)/p0_1

run_p0_2: chain_test p0_2_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_2 \
		p0_composability/p0_2_module_boundary/out/simv.daidir \
		p0_composability/p0_2_module_boundary/out/waves.fsdb \
		top.y 10ns $(BUILD)/p0_2

run_p0_3: chain_test p0_3_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_3 \
		p0_composability/p0_3_generate_for/out/simv.daidir \
		p0_composability/p0_3_generate_for/out/waves.fsdb \
		'top.y[2]' 10ns $(BUILD)/p0_3

run_p0_4: chain_test p0_4_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_4 \
		../../testdata/combined/interface_port_root/out/simv.daidir \
		../../testdata/combined/interface_port_root/out/waves.fsdb \
		if_root_tb.u_sink.observed_q 30ns $(BUILD)/p0_4

run_p0_5: chain_test p0_5_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_5 \
		p0_composability/p0_5_mux_branch/out/simv.daidir \
		p0_composability/p0_5_mux_branch/out/waves.fsdb \
		top.y 10ns $(BUILD)/p0_5

run_p0_5_probe: chain_test p0_5_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_5_probe \
		p0_composability/p0_5_mux_branch/out/simv.daidir \
		p0_composability/p0_5_mux_branch/out/waves.fsdb \
		top.y 20ns $(BUILD)/p0_5_probe

run_p0_6: chain_test p0_6_fixture
	$(PYTHON) run_kdebug_chain.py $(KDEBUG) p0_6 \
		p0_composability/p0_6_procedural_for/out/simv.daidir \
		p0_composability/p0_6_procedural_for/out/waves.fsdb \
		top.y 15ns $(BUILD)/p0_6
