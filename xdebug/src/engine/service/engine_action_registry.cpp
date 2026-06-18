#include "engine_action_registry.h"
#include "engine_globals.h"

#include "../../combined/active_trace_service.h"
#include "../../combined/active_trace_chain.h"
#include "../../api/text_response_builder.h"

#include <memory>
#include <sstream>

namespace xdebug_design {

// Registration functions from per-category handler files.
void register_waveform_handlers(EngineActionRegistry& r);
void register_protocol_handlers(EngineActionRegistry& r);
void register_design_handlers(EngineActionRegistry& r);

// ═══════════════════════════════════════════════════════════════════════
// Combined action handlers (simple wrappers — kept here for visibility)
// ═══════════════════════════════════════════════════════════════════════

namespace {

class ActiveDriverHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        xdebug::ActiveTraceService svc;
        return svc.run_engine(request, g_daidir_path, g_fsdb_path, g_fsdb_file);
    }
    std::string render_xout(const Json& r) const override {
        std::string base = EngineActionHandler::render_xout(r);
        const Json& data = r.value("data", Json::object());
        xdebug::TextResponseBuilder out("xdebug");
        out.emit_header(action_name());
        // Render base content then append driver detail
        std::ostringstream oss;
        oss << base << "\n";
        for (const char* key : {"driver","path","statements","controls","events"}) {
            if (!data.contains(key)) continue;
            oss << key << ":\n";
            if (data[key].is_array()) {
                for (const auto& item : data[key])
                    oss << "  " << xdebug::json_to_xout_value(item) << "\n";
            } else if (data[key].is_object()) {
                for (auto it = data[key].begin(); it != data[key].end(); ++it)
                    oss << "  " << it.key() << ": " << xdebug::json_to_xout_value(it.value()) << "\n";
            }
        }
        if (data.contains("limitations") && data["limitations"].is_array() && !data["limitations"].empty()) {
            oss << "limitations:\n";
            for (const auto& l : data["limitations"])
                oss << "  " << l.get<std::string>() << "\n";
        }
        return oss.str();
    }
};

class ActiveDriverChainHandler : public EngineActionHandler {
public:
    const char* action_name() const override { return "trace.active_driver_chain"; }
    bool needs_design() const override { return true; }
    bool needs_waveform() const override { return true; }
    Json run(const Json& request) const override {
        xdebug::ActiveTraceChainService svc;
        return svc.run_engine(request, g_daidir_path, g_fsdb_path, g_fsdb_file);
    }
};

class NotImplementedHandler : public EngineActionHandler {
    std::string name_;
    bool nd_, nw_;
public:
    NotImplementedHandler(const char* name, bool needs_design, bool needs_waveform)
        : name_(name), nd_(needs_design), nw_(needs_waveform) {}
    const char* action_name() const override { return name_.c_str(); }
    bool needs_design() const override { return nd_; }
    bool needs_waveform() const override { return nw_; }
    Json run(const Json&) const override {
        Json e; e["error"] = "NOT_IMPLEMENTED";
        e["message"] = "action not yet implemented in unified engine: " + name_;
        return e;
    }
};

static void add_ni(EngineActionRegistry& r, const char* name,
                   bool nd, bool nw) {
    r.add(std::unique_ptr<EngineActionHandler>(
        new NotImplementedHandler(name, nd, nw)));
}

} // namespace

// ═══════════════════════════════════════════════════════════════════════
// Registry implementation
// ═══════════════════════════════════════════════════════════════════════

void EngineActionRegistry::add(std::unique_ptr<EngineActionHandler> handler) {
    if (!handler) return;
    handlers_[handler->action_name()] = std::move(handler);
}

const EngineActionHandler* EngineActionRegistry::find(const std::string& action) const {
    auto it = handlers_.find(action);
    return it != handlers_.end() ? it->second.get() : nullptr;
}

const EngineActionRegistry& engine_action_registry() {
    static EngineActionRegistry* reg = []() {
        auto* r = new EngineActionRegistry();

        // ── Design handlers ──
        register_design_handlers(*r);

        // ── Waveform handlers ──
        register_waveform_handlers(*r);

        // ── Protocol handlers ──
        register_protocol_handlers(*r);

        // ── Combined handlers ──
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverHandler));
        r->add(std::unique_ptr<EngineActionHandler>(new ActiveDriverChainHandler));

        return r;
    }();
    return *reg;
}

} // namespace xdebug_design
