TOP ?= ..

include $(TOP)/mk/common_flags.mk
include $(TOP)/mk/npi.mk

CXXFLAGS = $(COMMON_CXXFLAGS) $(NPI_CXXFLAGS) -Isrc -Isrc/core -Isrc/design -Isrc/waveform -Ithird_party
LDFLAGS  = $(NPI_LDFLAGS)
BUILD    = build
LIBEXEC  = libexec
EXE      = xdebug

CORE_SRCS = src/core/common/tool_config.cpp \
            src/core/common/path_utils.cpp \
            src/core/session/session_types.cpp \
            src/core/ai/ai_response.cpp

APP_SRCS = src/main.cpp \
           src/api/request_parser.cpp \
           src/api/response.cpp \
           src/api/action_catalog.cpp \
           src/api/dispatcher.cpp \
           src/session/session_store.cpp \
           src/backend/engine_adapter.cpp \
           src/runtime/work_dir.cpp \
           src/combined/active_trace_service.cpp

DESIGN_SRCS = src/design/main.cpp \
              src/design/session/session_registry.cpp \
              src/design/session/session_manager.cpp \
              src/design/session/session_transport.cpp \
              src/design/client/client.cpp \
              src/design/commands/cmd_ai.cpp \
              src/design/service/action_support.cpp \
              src/design/service/trace_actions.cpp \
              src/design/service/graph_actions.cpp \
              src/design/service/source_actions.cpp \
              src/design/service/semantic_actions.cpp \
              src/design/service/port_actions.cpp \
              src/design/service/router.cpp \
              src/design/server/server.cpp \
              src/design/common/xdebug_design_paths.cpp \
              src/design/ast/ast_extractor.cpp \
              src/design/port/port_analyzer.cpp \
              src/design/control_dep/control_dep.cpp \
              src/design/trace/trace_engine.cpp \
              src/design/signal/signal_finder.cpp

WAVEFORM_SRCS = src/waveform/main.cpp \
                src/waveform/session/session_registry.cpp \
                src/waveform/session/session_manager.cpp \
                src/waveform/session/session_transport.cpp \
                src/waveform/client/client.cpp \
                src/waveform/commands/cmd_ai.cpp \
                src/waveform/service/action_support.cpp \
                src/waveform/service/config_support.cpp \
                src/waveform/service/router.cpp \
                src/waveform/server/server.cpp \
                src/waveform/server/service/context.cpp \
                src/waveform/server/service/value_scope.cpp \
                src/waveform/server/service/signal_analysis.cpp \
                src/waveform/server/service/signal_inspect.cpp \
                src/waveform/server/service/query_actions.cpp \
                src/waveform/server/service/event_handlers.cpp \
                src/waveform/server/service/request_router.cpp \
                src/waveform/server/fsdb_value_reader.cpp \
                src/waveform/server/fsdb_scan_utils.cpp \
                src/waveform/list/list_manager.cpp \
                src/waveform/cursor/cursor_manager.cpp \
                src/waveform/common/xdebug_waveform_paths.cpp \
                src/waveform/common/time_spec.cpp \
                src/waveform/common/time_parser.cpp \
                src/waveform/apb/apb_manager.cpp \
                src/waveform/apb/apb_analyzer.cpp \
                src/waveform/axi/axi_manager.cpp \
                src/waveform/axi/axi_analyzer.cpp \
                src/waveform/event/event_manager.cpp \
                src/waveform/event/event_expr.cpp \
                src/waveform/event/event_analyzer.cpp

CORE_OBJS = $(CORE_SRCS:%.cpp=$(BUILD)/%.o)
APP_OBJS = $(APP_SRCS:%.cpp=$(BUILD)/%.o)
DESIGN_OBJS = $(DESIGN_SRCS:%.cpp=$(BUILD)/%.o)
WAVEFORM_OBJS = $(WAVEFORM_SRCS:%.cpp=$(BUILD)/%.o)

.PHONY: all internal-engines unit-test clean

all: $(EXE) internal-engines

internal-engines: $(LIBEXEC)/xdebug-design-engine $(LIBEXEC)/xdebug-waveform-engine

$(EXE): $(APP_OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

$(LIBEXEC)/xdebug-design-engine: $(CORE_OBJS) $(DESIGN_OBJS)
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -o $@ $^ $(LDFLAGS)

$(LIBEXEC)/xdebug-waveform-engine: $(CORE_OBJS) $(WAVEFORM_OBJS)
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -o $@ $^ $(LDFLAGS)

$(BUILD)/%.o: %.cpp
	mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -DXDEBUG_INTERNAL_ENGINE -c -o $@ $<

unit-test: $(CORE_OBJS)
	mkdir -p $(BUILD)/tests
	$(CXX) $(CXXFLAGS) -o $(BUILD)/tests/test_core_types tests/unit/test_core_types.cpp $(CORE_OBJS)
	$(BUILD)/tests/test_core_types

clean:
	rm -rf $(BUILD) $(LIBEXEC) $(EXE)
