#include "stream_manager.h"

#include "../common/kdebug_waveform_paths.h"

#include <fcntl.h>
#include <cstdio>
#include <fstream>
#include <map>
#include <set>
#include <sys/file.h>
#include <unistd.h>

namespace kdebug_waveform {

namespace {

bool lock_file(int fd) {
    return flock(fd, LOCK_EX) == 0;
}

void unlock_file(int fd) {
    flock(fd, LOCK_UN);
}

Json storage_json(const std::vector<StreamConfig>& configs) {
    Json root;
    root["version"] = 1;
    root["streams"] = Json::array();
    for (const auto& config : configs) root["streams"].push_back(stream_config_json(config));
    return root;
}

} // namespace

bool load_stream_config_arg(const Json& args, Json& root, std::string& error) {
    if (args.contains("streams")) {
        if (!args["streams"].is_array()) {
            error = "args.streams must be an array";
            return false;
        }
        root = Json{{"streams", args["streams"]}};
        return true;
    }
    if (args.contains("config")) {
        if (!args["config"].is_object()) {
            error = "args.config must be an object";
            return false;
        }
        root = args["config"];
        return true;
    }
    std::string path = args.value("config_path", args.value("file", std::string()));
    if (path.empty()) {
        error = "stream.config.load requires args.streams, args.config, args.config_path, or args.file";
        return false;
    }
    std::ifstream input(path.c_str());
    if (!input) {
        error = "config file not found: " + path;
        return false;
    }
    try {
        input >> root;
    } catch (const std::exception& e) {
        error = std::string("invalid JSON in stream config file: ") + e.what();
        return false;
    }
    if (!root.is_object()) {
        error = "stream config file must contain a JSON object";
        return false;
    }
    return true;
}

bool parse_stream_config_list(const Json& root, std::vector<StreamConfig>& streams, std::string& error) {
    streams.clear();
    Json arr;
    if (root.is_array()) arr = root;
    else if (root.is_object() && root.contains("streams")) arr = root["streams"];
    else {
        error = "stream config requires a streams array";
        return false;
    }
    if (!arr.is_array() || arr.empty()) {
        error = "stream config streams must be a non-empty array";
        return false;
    }
    std::set<std::string> names;
    for (const auto& item : arr) {
        StreamConfig config;
        if (!parse_stream_config_json(item, config, error)) return false;
        if (!names.insert(config.name).second) {
            error = "duplicate stream name in config: " + config.name;
            return false;
        }
        streams.push_back(config);
    }
    return true;
}

bool StreamManager::load_session(const std::string& session_id, std::vector<StreamConfig>& configs) {
    configs.clear();
    int fd = open(kdebug_waveform_streams_path(session_id).c_str(), O_RDONLY);
    if (fd < 0) return true;
    if (!lock_file(fd)) {
        close(fd);
        return false;
    }
    FILE* fp = fdopen(fd, "r");
    if (!fp) {
        unlock_file(fd);
        close(fd);
        return false;
    }
    std::string text;
    char buf[4096];
    while (fgets(buf, sizeof(buf), fp)) text += buf;
    fclose(fp);
    if (text.empty()) return true;
    try {
        Json root = Json::parse(text);
        std::string error;
        return parse_stream_config_list(root, configs, error);
    } catch (...) {
        return false;
    }
}

bool StreamManager::save_session(const std::string& session_id, const std::vector<StreamConfig>& configs) {
    if (!kdebug_waveform_ensure_session_dir(session_id)) return false;
    int fd = open(kdebug_waveform_streams_path(session_id).c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return false;
    if (!lock_file(fd)) {
        close(fd);
        return false;
    }
    std::string data = storage_json(configs).dump(2) + "\n";
    bool ok = write(fd, data.c_str(), data.size()) == static_cast<ssize_t>(data.size());
    unlock_file(fd);
    close(fd);
    return ok;
}

bool StreamManager::load_configs(const std::string& session_id, const std::vector<StreamConfig>& incoming,
                                 const std::string& mode, std::string& error) {
    if (mode != "replace" && mode != "append") {
        error = "stream.config.load mode must be replace or append";
        return false;
    }
    std::vector<StreamConfig> current;
    if (!load_session(session_id, current)) {
        error = "failed to load existing stream config";
        return false;
    }
    if (mode == "append") {
        std::set<std::string> names;
        for (const auto& item : current) names.insert(item.name);
        for (const auto& item : incoming) {
            if (!names.insert(item.name).second) {
                error = "stream already exists: " + item.name;
                return false;
            }
            current.push_back(item);
        }
        return save_session(session_id, current);
    }

    std::map<std::string, StreamConfig> by_name;
    for (const auto& item : current) by_name[item.name] = item;
    for (const auto& item : incoming) by_name[item.name] = item;
    std::vector<StreamConfig> out;
    for (const auto& kv : by_name) out.push_back(kv.second);
    return save_session(session_id, out);
}

bool StreamManager::get_stream(const std::string& session_id, const std::string& name, StreamConfig& config) {
    std::vector<StreamConfig> configs;
    if (!load_session(session_id, configs)) return false;
    for (const auto& item : configs) {
        if (item.name == name) {
            config = item;
            return true;
        }
    }
    return false;
}

std::vector<StreamConfig> StreamManager::list_streams(const std::string& session_id) {
    std::vector<StreamConfig> configs;
    load_session(session_id, configs);
    return configs;
}

} // namespace kdebug_waveform
