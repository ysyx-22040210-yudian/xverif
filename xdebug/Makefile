TOP ?= ..

include $(TOP)/mk/common_flags.mk

CXXFLAGS = $(COMMON_CXXFLAGS) -pthread -Isrc -Isrc/core -Isrc/design -Isrc/waveform -Ithird_party
LDFLAGS  = -pthread
DEPFLAGS = -MMD -MP
# Frontend does not need NPI (all NPI is in the engine subprocess).
FRONTEND_LDFLAGS = -pthread
BUILD    = build
LIBEXEC  = libexec
EXE      = xdebug
PYTHON  ?= python3
AXI_REFERENCE_ROOT ?= /home/yian/axi_test/test
SVT_VIP_INCDIR ?= /home/yian/axi_test/test/include/sverilog
SVT_VIP_SRCDIR ?= /home/yian/axi_test/test/src/sverilog/vcs

CORE_SRCS = src/core/common/tool_config.cpp \
            src/core/common/path_utils.cpp \
            src/core/transport/file_exchange.cpp \
            src/core/logging/action_log.cpp \
            src/core/session/session_types.cpp \
            src/core/process/process_runner.cpp \
            src/core/ai/ai_response.cpp

API_SUPPORT_SRCS = src/api/action_spec.cpp \
                   src/api/action_registry.cpp \
                   src/api/action_registry_init.cpp \
                   src/api/request_envelope.cpp \
                   src/api/request_validator.cpp \
                   src/api/resource_resolver.cpp \
                   src/api/response_builder.cpp

APP_SRCS = src/main.cpp \
           src/api/request_parser.cpp \
           src/api/response.cpp \
           src/api/help_text.cpp \
           src/api/text_response_builder.cpp \
           src/api/xout_renderer.cpp \
           src/api/action_catalog.cpp \
           src/api/dispatcher.cpp \
           src/api/stdio_loop.cpp \
           $(API_SUPPORT_SRCS) \
           src/session/session_catalog.cpp \
           src/backend/engine_adapter.cpp \
           src/runtime/work_dir.cpp

CORE_OBJS = $(CORE_SRCS:%.cpp=$(BUILD)/%.o)
API_SUPPORT_OBJS = $(API_SUPPORT_SRCS:%.cpp=$(BUILD)/%.o)
APP_OBJS = $(APP_SRCS:%.cpp=$(BUILD)/%.o)
DEPS = $(sort $(CORE_OBJS:.o=.d) \
       $(API_SUPPORT_OBJS:.o=.d) \
       $(APP_OBJS:.o=.d) \
       $(BUILD)/src/waveform/service/rc_generator.d \
       $(BUILD)/src/waveform/value/logic_value.d \
       $(BUILD)/src/session/session_catalog.d)

.PHONY: all internal-engines audit-no-cpp-npi unit-test log-test test-infra pytest-contract pytest-synthetic-existing pytest-counter-statistics pytest-axi-vip pytest-apb-vip pytest-active-semantics pytest-realdata pytest-session pytest-mcp test-fast test-contract test-synthetic test-vip test-active-trace test-session test-mcp-direct test-mcp-fake-lsf test-realdata-smoke test-regression test-nightly test-mcp-real-lsf mcp-test schema-test contract-test combined-test clean

all: audit-no-cpp-npi $(EXE) internal-engines

internal-engines: $(LIBEXEC)/xdebug-engine

audit-no-cpp-npi:
	@if grep -RInE '#include[[:space:]]+[<"]npi(_[^>"]*)?\.h[>"]|#include[[:space:]]+[<"]npi(_fsdb|_hdl|_L1)[^>"]*[>"]|\bnpi(Fsdb|Handle)\b|\bnpi_(init|end|get|handle|release|fsdb|active|trace)[A-Za-z0-9_]*[[:space:]]*\(' src 2>/dev/null; then \
		echo "ERROR: xdebug C++ sources must not include Verdi NPI headers; use tcl_engine/xdebug_npi.tcl instead." >&2; \
		exit 1; \
	fi

# Tcl NPI backend: keep the public C++ CLI, but run Verdi/NPI through Tcl.
$(LIBEXEC)/xdebug-engine: tcl_engine/xdebug-engine tcl_engine/xdebug_engine.py tcl_engine/xdebug_npi.tcl
	mkdir -p $(dir $@)
	mkdir -p $(LIBEXEC)/tcl_engine
	cp tcl_engine/xdebug-engine $@
	cp tcl_engine/xdebug_engine.py $(LIBEXEC)/tcl_engine/xdebug_engine.py
	cp tcl_engine/xdebug_npi.tcl $(LIBEXEC)/tcl_engine/xdebug_npi.tcl
	chmod +x $@ $(LIBEXEC)/tcl_engine/xdebug_engine.py

$(EXE): $(CORE_OBJS) $(APP_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(FRONTEND_LDFLAGS)

$(BUILD)/%.o: %.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(DEPFLAGS) -DXDEBUG_INTERNAL_ENGINE -c -o $@ $<

unit-test: $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o $(BUILD)/src/waveform/service/rc_generator.o $(BUILD)/src/waveform/value/logic_value.o $(BUILD)/src/session/session_catalog.o
	mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_core_types tests/unit/test_core_types.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_core_types
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_log tests/unit/test_action_log.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_action_log
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_file_exchange tests/unit/test_file_exchange.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_file_exchange
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_process_runner tests/unit/test_process_runner.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_process_runner
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_session_catalog tests/unit/test_session_catalog.cpp $(BUILD)/src/session/session_catalog.o
	$(BUILD)/tests/test_session_catalog
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_registry tests/unit/test_action_registry.cpp $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o
	$(BUILD)/tests/test_action_registry
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_request_contract tests/unit/test_request_contract.cpp $(CORE_OBJS) $(API_SUPPORT_OBJS) $(BUILD)/src/api/response.o
	$(BUILD)/tests/test_request_contract
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_text_response_builder tests/unit/test_text_response_builder.cpp $(BUILD)/src/api/text_response_builder.o $(BUILD)/src/api/xout_renderer.o
	$(BUILD)/tests/test_text_response_builder
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_logic_value tests/unit/test_logic_value.cpp $(BUILD)/src/waveform/value/logic_value.o
	$(BUILD)/tests/test_logic_value
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_rc_generator tests/unit/test_rc_generator.cpp $(BUILD)/src/waveform/service/rc_generator.o
	$(BUILD)/tests/test_rc_generator

log-test: $(CORE_OBJS) $(EXE) internal-engines
	mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_action_log tests/unit/test_action_log.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_action_log
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session/test_stdio_loop_lifecycle.py
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session/test_session_lifecycle.py -k "engine_crash_marker_is_written_by_signal_handler"
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session/test_session_lifecycle.py -k "uds_direct_query_times_out_without_spawn_fallback or uds_connect_failure_is_logged or uds_invalid_json_response_is_logged"
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -q $(CURDIR)/../xverif_mcp/tests/test_stdio_loop_session_lifecycle.py

test-infra:
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/unit/test_test_infra.py

pytest-contract: $(EXE)
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/contract

pytest-synthetic-existing: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_existing_regressions.py

pytest-counter-statistics: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_counter_statistics.py

pytest-axi-vip: all
	AXI_REFERENCE_ROOT=$(AXI_REFERENCE_ROOT) SVT_VIP_INCDIR=$(SVT_VIP_INCDIR) SVT_VIP_SRCDIR=$(SVT_VIP_SRCDIR) \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_axi_vip_real.py

pytest-apb-vip: all
	SVT_VIP_INCDIR=$(SVT_VIP_INCDIR) SVT_VIP_SRCDIR=$(SVT_VIP_SRCDIR) \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/synthetic/test_apb_vip_real.py

pytest-active-semantics: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/combined/test_active_semantics.py

pytest-realdata: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/realdata

pytest-session: all
	$(PYTHON) -m pytest -c tests/pytest.ini -q tests/session

pytest-mcp: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp

test-fast: test-infra schema-test unit-test contract-test pytest-contract

test-contract: test-fast

test-synthetic: pytest-synthetic-existing pytest-counter-statistics pytest-active-semantics

test-vip: pytest-axi-vip pytest-apb-vip

test-active-trace: pytest-active-semantics

test-session: pytest-session

test-mcp-direct: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp -m "mcp_direct"

test-mcp-fake-lsf: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp -m "mcp_fake_lsf"

test-realdata-smoke: pytest-realdata

test-regression: test-fast test-synthetic test-session test-mcp-direct test-mcp-fake-lsf test-realdata-smoke

test-nightly: test-regression test-vip
	@if [ "$$XDEBUG_ENABLE_REAL_LSF" = "1" ]; then \
		$(MAKE) test-mcp-real-lsf PYTHON=$(PYTHON); \
	else \
		echo "skip optional real LSF tests: set XDEBUG_ENABLE_REAL_LSF=1 and run make test-mcp-real-lsf"; \
	fi

test-mcp-real-lsf: all
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. XDEBUG_ENABLE_REAL_LSF=1 \
		$(PYTHON) -m pytest -c tests/pytest.ini -q tests/mcp -m "mcp_real_lsf"

schema-test:
	$(PYTHON) tools/validate_schema.py schemas/v1
	$(PYTHON) tools/validate_examples.py examples schemas/v1

mcp-test:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) $(CURDIR)/../xverif_mcp/tools/test_actions.py

mcp-test-schema:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) $(CURDIR)/../xverif_mcp/tools/test_actions.py --schema-only

mcp-test-lsf:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. XVERIF_MCP_BACKEND=lsf XVERIF_MCP_FAKE_LSF=1 $(PYTHON) $(CURDIR)/../xverif_mcp/tools/test_actions.py

mcp-session-test:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) -m pytest -q $(CURDIR)/../xverif_mcp/tests/test_stdio_loop_session_lifecycle.py $(CURDIR)/../xverif_mcp/tests/test_backend_wiring.py $(CURDIR)/../xverif_mcp/tests/test_session_errors.py -v

mcp-sdk-test:
	PYTHONPATH=$(CURDIR)/../xverif_mcp/src:$(CURDIR)/.. $(PYTHON) -m pytest -q $(CURDIR)/../xverif_mcp/tests/test_mcp_sdk_smoke.py -v

mcp-inspect:
	cd $(CURDIR)/.. && PYTHONPATH=xverif_mcp/src$(PYTHON) -m mcp dev xverif_mcp/src/xverif_mcp/server.py

mcp-run:
	cd $(CURDIR)/.. && PYTHONPATH=xverif_mcp/src$(PYTHON) -m mcp run xverif_mcp/src/xverif_mcp/server.py

contract-test: $(EXE) schema-test
	$(PYTHON) tools/audit_action_schema_coverage.py $(CURDIR)
	$(PYTHON) tools/check_action_contract.py specs/actions $(CURDIR)/$(EXE)

combined-test: $(EXE)
	$(PYTHON) tests/combined/run_active_driver_fixture.py

clean:
	rm -rf $(BUILD) $(LIBEXEC) $(EXE)

-include $(DEPS)
