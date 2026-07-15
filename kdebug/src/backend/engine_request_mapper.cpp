#include "backend/engine_request_mapper.h"
#include "backend/engine_adapter.h"

namespace kdebug {

Json EngineRequestMapper::map(EngineKind kind, const Json& request) const {
    Json forwarded = request;
    forwarded["api_version"] = "kdebug.internal.v1";

    if (forwarded.contains("target") && forwarded["target"].is_object()) {
        if (kind == EngineKind::Design) {
            // Design engine uses "dbdir" (not "daidir")
            if (forwarded["target"].contains("daidir")) {
                forwarded["target"]["dbdir"] = forwarded["target"]["daidir"];
                forwarded["target"].erase("daidir");
            }
            // Design engine doesn't need fsdb
            forwarded["target"].erase("fsdb");
        } else {
            // Waveform engine doesn't need daidir
            forwarded["target"].erase("daidir");
        }
    }
    return forwarded;
}

} // namespace kdebug
