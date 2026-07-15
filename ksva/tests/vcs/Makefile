# ksva VCS 语义验证 Makefile
# 编译选项参考 ~/xring/dv/cfg/Makefile
# Usage:
#   make cmp   CASE=simple_impl   # compile
#   make run   CASE=simple_impl   # run
#   make all                     # all cases compile + run

VCS      ?= vcs
VLOGAN   ?= vlogan
CASE     ?= simple_impl

ROOT_DIR   = $(CURDIR)
CASE_DIR   = $(ROOT_DIR)/cases/$(CASE)
TB_DIR     = $(ROOT_DIR)/tb
OUT_DIR    = $(ROOT_DIR)/out/$(CASE)
BUILD_DIR  = $(OUT_DIR)/build
ANDB_DIR   = $(BUILD_DIR)/work
SIMV       = $(BUILD_DIR)/simv

VCS_SHARED = -full64 -sverilog \
             -timescale=1ns/1ps \
             -kdb -lca \
             +define+KSVA_VCS_TEST

SIM_OPTS   = +fsdb+force +fsdb+autoflush +fsdbfile+waves.fsdb \
             -ucli -do $(ROOT_DIR)/wave.tcl \
             -l sim.log

.PHONY: cmp run clean all

cmp:
	@echo "[ksva VCS] compiling $(CASE)..."
	@mkdir -p $(ANDB_DIR)
	cd $(ANDB_DIR) && $(VLOGAN) $(VCS_SHARED) \
		$(CASE_DIR)/dut.sv \
		$(CASE_DIR)/assertions.sv \
		$(TB_DIR)/ksva_vcs_tb.sv \
		-l $(BUILD_DIR)/vlogan.log
	cd $(ANDB_DIR) && $(VCS) -full64 -sverilog \
		-debug_access+all -kdb -lca \
		-timescale=1ns/1ps \
		-top ksva_vcs_tb \
		-o $(SIMV) -l $(BUILD_DIR)/elab.log

run:
	@if [ ! -f $(SIMV) ]; then \
		echo "Run 'make cmp CASE=$(CASE)' first."; exit 1; \
	fi
	@echo "[ksva VCS] running $(CASE)..."
	@mkdir -p $(OUT_DIR)
	cd $(OUT_DIR) && $(SIMV) $(SIM_OPTS)
	@echo ""
	@grep -i "assertion\|failure\|Summary" $(OUT_DIR)/sim.log 2>/dev/null || true

all:
	@for case_dir in $(ROOT_DIR)/cases/*/; do \
		c=$$(basename $$case_dir); \
		$(MAKE) cmp CASE=$$c 2>&1 | tail -1; \
		$(MAKE) run CASE=$$c 2>&1 | tail -3; \
	done

clean:
	rm -rf $(OUT_DIR)
