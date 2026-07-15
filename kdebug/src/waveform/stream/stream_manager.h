#pragma once

#include "stream_config.h"

#include <string>
#include <vector>

namespace kdebug_waveform {

class StreamManager {
public:
    bool load_session(const std::string& session_id, std::vector<StreamConfig>& configs);
    bool save_session(const std::string& session_id, const std::vector<StreamConfig>& configs);
    bool load_configs(const std::string& session_id, const std::vector<StreamConfig>& incoming,
                      const std::string& mode, std::string& error);
    bool get_stream(const std::string& session_id, const std::string& name, StreamConfig& config);
    std::vector<StreamConfig> list_streams(const std::string& session_id);
};

bool load_stream_config_arg(const Json& args, Json& root, std::string& error);
bool parse_stream_config_list(const Json& root, std::vector<StreamConfig>& streams, std::string& error);

} // namespace kdebug_waveform
