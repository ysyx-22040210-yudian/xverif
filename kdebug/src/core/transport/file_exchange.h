#pragma once

#include "json.hpp"

#include <string>

namespace kdebug_core {

using Json = nlohmann::json;

static const char* const kFileRpcVersion = "kdebug-file-rpc-v1";

enum class AtomicWriteMode {
    Replace,
    CreateNew
};

struct AtomicWriteResult {
    bool ok = false;
    int err = 0;
    std::string path;
    std::string tmp_path;
    std::string message;
};

struct FileExchangeResult {
    bool ok = false;
    std::string request_id;
    std::string status;
    std::string message;
    long elapsed_ms = 0;
    Json response;
    Json response_wrapper;
};

struct FileClaimResult {
    bool claimed = false;
    bool ready = false;
    std::string request_id;
    std::string claim_path;
    std::string status;
    std::string message;
    Json wrapper;
    Json request;
};

std::string file_transport_dir(const std::string& session_dir);

bool ensure_file_transport_layout(const std::string& dir);

bool atomic_write_json_file(const std::string& path, const Json& payload);

AtomicWriteResult atomic_write_json_file_ex(const std::string& path,
                                            const Json& payload,
                                            AtomicWriteMode mode = AtomicWriteMode::Replace,
                                            const std::string& tmp_dir = std::string());

std::string make_file_request_id();

FileExchangeResult file_exchange_send_request(const std::string& dir,
                                               const Json& request,
                                               int timeout_ms = 2000);

FileClaimResult file_exchange_claim_one(const std::string& dir,
                                        const std::string& agent_id);

bool file_exchange_complete_claim(const std::string& dir,
                                  const FileClaimResult& claim,
                                  const Json& response,
                                  bool ok,
                                  const std::string& status,
                                  const std::string& message,
                                  const Json& worker,
                                  const Json& error = Json::object());

int file_exchange_scan_stale_claims(const std::string& dir,
                                    const std::string& agent_id,
                                    long long claim_timeout_ms);

int file_exchange_gc(const std::string& dir);

long long file_exchange_now_us();

int file_exchange_poll_interval_ms();
int file_exchange_max_json_bytes();
int file_exchange_claim_timeout_ms(int request_timeout_ms);
bool file_exchange_keep_history();

} // namespace kdebug_core
