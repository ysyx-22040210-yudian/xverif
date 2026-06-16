TOP ?= ../../..

include $(TOP)/mk/common_flags.mk
include $(TOP)/mk/npi.mk

CXXFLAGS += $(NPI_CXXFLAGS) -I.
LDFLAGS  += $(NPI_LDFLAGS) -Wl,-rpath,$(NPI_LIB)

BUILD := build

.PHONY: all clean chain_test probe \
        p0_0_fixture p0_1_fixture p0_2_fixture p0_3_fixture \
        p0_5_fixture p0_6_fixture

all: chain_test

chain_test: chain_test.cpp chain_test.h
	mkdir -p $(BUILD)
	$(CXX) $(CXXFLAGS) -o $(BUILD)/$@ chain_test.cpp $(LDFLAGS)

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
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_0_assign_chain/out/simv.daidir \
		-ssf p0_composability/p0_0_assign_chain/out/waves.fsdb \
		-signal top.out -time 10ns

run_p0_1: chain_test p0_1_fixture
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_1_flop_boundary/out/simv.daidir \
		-ssf p0_composability/p0_1_flop_boundary/out/waves.fsdb \
		-signal top.out -time 17ns

run_p0_2: chain_test p0_2_fixture
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_2_module_boundary/out/simv.daidir \
		-ssf p0_composability/p0_2_module_boundary/out/waves.fsdb \
		-signal top.y -time 10ns

run_p0_3: chain_test p0_3_fixture
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_3_generate_for/out/simv.daidir \
		-ssf p0_composability/p0_3_generate_for/out/waves.fsdb \
		-signal top.y[2] -time 10ns

run_p0_4: chain_test p0_4_fixture
	$(BUILD)/chain_test \
		-dbdir ../../testdata/combined/interface_port_root/out/simv.daidir \
		-ssf ../../testdata/combined/interface_port_root/out/waves.fsdb \
		-signal if_root_tb.u_sink.observed_q -time 30ns

run_p0_5: chain_test p0_5_fixture
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_5_mux_branch/out/simv.daidir \
		-ssf p0_composability/p0_5_mux_branch/out/waves.fsdb \
		-signal top.y -time 10ns

run_p0_5_probe: chain_test p0_5_fixture
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_5_mux_branch/out/simv.daidir \
		-ssf p0_composability/p0_5_mux_branch/out/waves.fsdb \
		-signal top.y -time 20ns --mode=probe

run_p0_6: chain_test p0_6_fixture
	$(BUILD)/chain_test \
		-dbdir p0_composability/p0_6_procedural_for/out/simv.daidir \
		-ssf p0_composability/p0_6_procedural_for/out/waves.fsdb \
		-signal top.y -time 15ns
