#pragma once
#include <curl/curl.h>
#include <nlohmann/json.hpp>
#include "cfss/http_utils.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/hash.hpp"

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <ctime>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

namespace cfss::telegram {

struct HttpResult {
    CURLcode transport{CURLE_FAILED_INIT};
    long http_status{0};
    long request_size{0};
    std::string body;
    std::string error;
};

struct SendResult {
    std::string status;
    long http_status{0};
    long message_id{0};
    std::string detail;
};

inline std::size_t append_body(char* data, std::size_t size, std::size_t count, void* context) {
    if (size != 0U && count > static_cast<std::size_t>(-1) / size) return 0U;
    const auto bytes = size * count;
    if (!context) return 0U;
    static_cast<std::string*>(context)->append(data, bytes);
    return bytes;
}

inline HttpResult perform_http(const std::string& url, const std::string* payload = nullptr) {
    HttpResult result;
    CURL* curl = curl_easy_init();
    if (!curl) {
        result.error = "curl_init_failed";
        return result;
    }
    char error_buffer[CURL_ERROR_SIZE]{};
    curl_slist* headers = nullptr;
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, append_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &result.body);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, error_buffer);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "CFSS-CXX20/1.0");
    if (payload) {
        headers = curl_slist_append(headers, "Content-Type: application/json");
        if (!headers) {
            curl_easy_cleanup(curl);
            result.error = "curl_headers_allocation_failed";
            return result;
        }
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload->c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(payload->size()));
    }
    result.transport = curl_easy_perform(curl);
    curl_easy_getinfo(curl, CURLINFO_REQUEST_SIZE, &result.request_size);
    if (result.transport == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &result.http_status);
    if (error_buffer[0] != '\0') result.error = error_buffer;
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    return result;
}

inline std::string stable_fingerprint(std::string_view text) {
    // FNV-1a 64-bit is used only as a deterministic deduplication fingerprint, not as a security hash.
    std::uint64_t hash = 14695981039346656037ULL;
    for (const char raw_ch : text) {
        const auto ch = static_cast<unsigned char>(raw_ch);
        hash ^= static_cast<std::uint64_t>(ch);
        hash *= 1099511628211ULL;
    }
    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0') << hash;
    return out.str();
}

inline void write_json_atomic(const std::filesystem::path& path, const nlohmann::json& value) {
    write_file_atomic(path, value.dump(2) + "\n");
}

inline nlohmann::json load_json_or_default(const std::filesystem::path& path,
                                           const nlohmann::json& fallback) {
    if (!std::filesystem::exists(path)) return fallback;
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("state_file_open_failed");
    const std::string raw{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
    const auto parsed = nlohmann::json::parse(raw);
    if (!parsed.is_object()) throw std::runtime_error("state_file_root_invalid");
    return parsed;
}

inline std::string state_fa(const std::string& state) {
    if (state == "BUY_NOW") return "خرید فوری";
    if (state == "SELL_NOW") return "فروش فوری";
    if (state == "CONDITIONAL_BUY") return "خرید مشروط";
    if (state == "CONDITIONAL_SELL") return "فروش مشروط";
    if (state == "WATCHLIST") return "فهرست پایش";
    if (state == "NO_QUALIFIED_SETUP") return "بدون موقعیت معتبر";
    if (state == "MARKET_DATA_DEGRADED") return "اختلال یا نقص داده";
    return "وضعیت ناشناخته";
}

inline std::vector<std::string> build_status_messages(const nlohmann::json& artifact,
                                                       std::size_t rows_per_message = 20U) {
    if (!artifact.is_object() || artifact.value("artifact_type", std::string{}) != "cfss_l2_status_v1")
        throw std::invalid_argument("telegram_rejects_unknown_l2_artifact");
    if (!artifact.contains("source_run_id") || !artifact.at("source_run_id").is_string() ||
        !artifact.contains("source_scan_id") || !artifact.at("source_scan_id").is_string() ||
        !artifact.contains("instruments") || !artifact.at("instruments").is_array() ||
        artifact.at("instruments").empty())
        throw std::invalid_argument("telegram_l2_artifact_incomplete");
    if (rows_per_message == 0U || rows_per_message > 25U)
        throw std::invalid_argument("telegram_chunk_size_out_of_range");

    const auto& instruments = artifact.at("instruments");
    for (const auto& row : instruments) {
        const auto state = row.value("state", std::string{});
        const bool actionable = row.value("actionable", false);
        if (actionable || state == "BUY_NOW" || state == "SELL_NOW") {
            throw std::invalid_argument("stage1_delivery_blocks_unvalidated_actionable_signal");
        }
        if (state != "CONDITIONAL_BUY" && state != "CONDITIONAL_SELL" &&
            state != "WATCHLIST" && state != "NO_QUALIFIED_SETUP" && state != "MARKET_DATA_DEGRADED")
            throw std::invalid_argument("telegram_c10_state_invalid");
    }

    const std::string scan_id = artifact.at("source_scan_id").get<std::string>();
    const auto total = instruments.size();
    const auto parts = (total + rows_per_message - 1U) / rows_per_message;
    std::vector<std::string> messages;
    messages.reserve(parts);
    for (std::size_t part = 0; part < parts; ++part) {
        std::ostringstream out;
        out << "گزارش وضعیت بازار | Stage 1\n"
            << "شناسه اسکن: " << scan_id.substr(5U, 12U) << "\n"
            << "بخش " << (part + 1U) << " از " << parts << "\n"
            << "این پیام گزارش داده است، نه دستور معامله.\n\n";
        const std::size_t begin = part * rows_per_message;
        const std::size_t end = std::min(begin + rows_per_message, total);
        for (std::size_t i = begin; i < end; ++i) {
            const auto& row = instruments.at(i);
            out << row.value("symbol", std::string{"UNKNOWN"}) << " | "
                << state_fa(row.value("state", std::string{})) << "\n";
        }
        messages.push_back(out.str());
    }
    return messages;
}

inline SendResult classify_send_response(CURLcode transport, long http_status,
                                          const std::string& body, const std::string& error) {
    if (transport != CURLE_OK) {
        if (transport == CURLE_OPERATION_TIMEDOUT || transport == CURLE_SEND_ERROR ||
            transport == CURLE_RECV_ERROR) {
            return {"DELIVERY_UNKNOWN", http_status, 0, error.empty()
                ? curl_easy_strerror(transport) : error};
        }
        return {"RETRYABLE_FAILURE", http_status, 0, error.empty()
            ? curl_easy_strerror(transport) : error};
    }
    if (http_status == 429 || http_status >= 500)
        return {"RETRYABLE_FAILURE", http_status, 0, body.substr(0, 240)};
    if (http_status < 200 || http_status >= 300)
        return {"PERMANENT_FAILURE", http_status, 0, body.substr(0, 240)};
    try {
        const auto parsed = nlohmann::json::parse(body);
        if (parsed.value("ok", false) && parsed.contains("result") &&
            parsed.at("result").contains("message_id") &&
            parsed.at("result").at("message_id").is_number_integer()) {
            return {"DELIVERED", http_status,
                parsed.at("result").at("message_id").get<long>(), {}};
        }
        return {"PERMANENT_FAILURE", http_status, 0,
            "telegram_api_ok_false_or_message_id_missing"};
    } catch (const std::exception&) {
        return {"DELIVERY_UNKNOWN", http_status, 0, "telegram_response_parse_failed"};
    }
}

inline SendResult send_message(const std::string& token, const std::string& chat_id,
                               const std::string& message) {
    const std::string endpoint = "https://api.telegram.org/bot" + token + "/sendMessage";
    const nlohmann::json payload = {{"chat_id", chat_id}, {"text", message}, {"disable_web_page_preview", true}};
    const std::string body = payload.dump();
    const auto response = perform_http(endpoint, &body);
    return classify_send_response(response.transport, response.http_status,
                                  response.body, response.error);
}

inline std::string delivery_idempotency_key(const std::string& scan_id, std::size_t part) {
    return scan_id + ":status:" + std::to_string(part);
}

inline nlohmann::json default_outbox() {
    return {{"schema_version", 1}, {"messages", nlohmann::json::object()}};
}

inline std::string reconcile_outbox_status(const std::string& status) {
    return status == "SENDING" ? "DELIVERY_UNKNOWN" : status;
}
inline std::string reconcile_inbound_status(const std::string& status) {
    return status == "REPLY_SENDING" ? "DELIVERY_UNKNOWN" : status;
}

inline bool outbox_should_send(const nlohmann::json& entry) {
    const auto status = entry.value("status", std::string{"PENDING"});
    const int attempts = entry.value("attempts", 0);
    if (status == "PENDING") return true;
    return status == "RETRYABLE_FAILURE" && attempts < 3;
}

inline int run_outbound(const nlohmann::json& artifact, const std::filesystem::path& outbox_path,
                        const std::string& token, const std::string& chat_id) {
    auto outbox = load_json_or_default(outbox_path, default_outbox());
    if (outbox.value("schema_version", 0) != 1 || !outbox.contains("messages") || !outbox.at("messages").is_object())
        throw std::runtime_error("telegram_outbox_schema_invalid");
    const auto messages = build_status_messages(artifact);
    const auto run_id = artifact.at("source_run_id").get<std::string>();
    const auto scan_id = artifact.at("source_scan_id").get<std::string>();
    bool delivery_problem = false;
    for (std::size_t i = 0; i < messages.size(); ++i) {
        const std::string key = delivery_idempotency_key(scan_id, i + 1U);
        const std::string fingerprint = stable_fingerprint(messages[i]);
        auto& entries = outbox["messages"];
        if (entries.contains(key)) {
            auto& entry = entries[key];
            const auto status = entry.value("status", std::string{});
            if (entry.value("payload_fingerprint", std::string{}) != fingerprint)
                throw std::runtime_error("outbox_idempotency_payload_conflict");
            if (reconcile_outbox_status(status) == "DELIVERY_UNKNOWN" && status == "SENDING") {
                entry["status"] = "DELIVERY_UNKNOWN";
                entry["updated_at_epoch_ms"] = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::system_clock::now().time_since_epoch()).count();
                entry["last_error"] = "previous_process_ended_while_sending";
                write_json_atomic(outbox_path, outbox);
                delivery_problem = true;
                continue;
            }
            if (status == "DELIVERED") continue;
            if (status == "DELIVERY_UNKNOWN" || status == "PERMANENT_FAILURE") {
                delivery_problem = true;
                continue;
            }
            if (!outbox_should_send(entry)) {
                if (status == "RETRYABLE_FAILURE") {
                    entry["status"] = "PERMANENT_FAILURE";
                    entry["last_error"] = "retry_budget_exhausted";
                    write_json_atomic(outbox_path, outbox);
                }
                delivery_problem = true;
                continue;
            }
        } else {
            entries[key] = {
                {"scan_id", scan_id}, {"source_run_id", run_id},
                {"payload_fingerprint", fingerprint}, {"status", "PENDING"}, {"attempts", 0},
                {"telegram_message_id", nullptr}, {"http_status", nullptr}, {"last_error", nullptr}
            };
        }

        auto& entry = entries[key];
        entry["status"] = "SENDING";
        entry["attempts"] = entry.value("attempts", 0) + 1;
        entry["updated_at_epoch_ms"] = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        write_json_atomic(outbox_path, outbox);

        const auto result = send_message(token, chat_id, messages[i]);
        entry["status"] = result.status;
        entry["http_status"] = result.http_status;
        entry["telegram_message_id"] = result.message_id > 0 ? nlohmann::json(result.message_id) : nlohmann::json(nullptr);
        entry["last_error"] = result.detail.empty() ? nlohmann::json(nullptr) : nlohmann::json(result.detail);
        entry["updated_at_epoch_ms"] = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        write_json_atomic(outbox_path, outbox);
        std::cout << "TELEGRAM_OUTBOX key=" << key << " status=" << result.status
                  << " http=" << result.http_status << " message_id=" << result.message_id << '\n';
        if (result.status == "RETRYABLE_FAILURE" || result.status == "PERMANENT_FAILURE" ||
            result.status == "DELIVERY_UNKNOWN") delivery_problem = true;
        std::this_thread::sleep_for(std::chrono::milliseconds(350));
    }
    return delivery_problem ? EXIT_FAILURE : EXIT_SUCCESS;
}

inline nlohmann::json default_inbound_state();

inline std::string utc_now_iso() {
    const auto now = std::chrono::system_clock::now();
    const auto seconds = std::chrono::system_clock::to_time_t(now);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &seconds);
#else
    gmtime_r(&seconds, &tm);
#endif
    char buffer[32]{};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buffer;
}

inline void sync_system_status_artifact(const std::filesystem::path& manifest_path,
                                         nlohmann::json& manifest) {
    const auto system_path = manifest_path.parent_path() / "system_status.json";
    if (!std::filesystem::exists(system_path)) return;
    auto system = load_json_or_default(system_path, nlohmann::json::object());
    for (const auto* key : {"run_status", "telegram_send_status", "telegram_receive_test_status",
                            "telegram_message_ids", "telegram_last_update_id", "error_summary"}) {
        if (manifest.contains(key)) system[key] = manifest[key];
    }
    system["updated_at_utc"] = utc_now_iso();
    write_json_atomic(system_path, system);
    const std::string raw = system.dump(2) + "\n";
    if (manifest.contains("artifact_manifest") && manifest["artifact_manifest"].contains("system_status")) {
        manifest["artifact_manifest"]["system_status"]["sha256"] = cfss::sha256_hex(raw);
        manifest["artifact_manifest"]["system_status"]["bytes"] = raw.size();
    }
}

inline void record_outbound_manifest(const std::filesystem::path& manifest_path,
                                     const std::filesystem::path& outbox_path,
                                     const std::string& scan_id) {
    auto manifest = load_json_or_default(manifest_path, nlohmann::json::object());
    const auto outbox = load_json_or_default(outbox_path, default_outbox());
    const std::string prefix = scan_id + ":status:";
    bool found = false, all_delivered = true, has_unknown = false, has_permanent = false;
    long long send_attempts = 0, send_retries = 0;
    nlohmann::json message_ids = nlohmann::json::array();
    for (auto it = outbox.at("messages").begin(); it != outbox.at("messages").end(); ++it) {
        if (it.key().rfind(prefix, 0U) != 0U) continue;
        found = true;
        const auto status = it.value().value("status", std::string{});
        const auto attempts = it.value().value("attempts", 0);
        send_attempts += attempts;
        send_retries += std::max(0, attempts - 1);
        if (status != "DELIVERED") all_delivered = false;
        if (status == "DELIVERY_UNKNOWN") has_unknown = true;
        if (status == "PERMANENT_FAILURE") has_permanent = true;
        if (it.value().contains("telegram_message_id") && it.value()["telegram_message_id"].is_number_integer())
            message_ids.push_back(it.value()["telegram_message_id"]);
    }
    const std::string status = !found ? "NOT_ATTEMPTED" :
        (all_delivered ? "DELIVERED" : (has_unknown ? "DELIVERY_UNKNOWN" :
         (has_permanent ? "PERMANENT_FAILURE" : "RETRYABLE_FAILURE")));
    manifest["telegram_send_status"] = status;
    manifest["telegram_message_ids"] = message_ids;
    manifest["retry_summary"]["telegram_send_attempts_total_for_scan"] = send_attempts;
    manifest["retry_summary"]["telegram_retry_attempts_total_for_scan"] = send_retries;
    if (status == "DELIVERED" && manifest.value("run_status", std::string{}) == "L1_L2_PASS")
        manifest["run_status"] = "L1_L2_L3_PASS";
    else if (status != "DELIVERED") {
        manifest["run_status"] = "L3_FAILED";
        manifest["error_summary"].push_back("telegram_outbound:" + status);
    }
    manifest["end_time_utc"] = utc_now_iso();
    sync_system_status_artifact(manifest_path, manifest);
    write_json_atomic(manifest_path, manifest);
}

inline void record_inbound_manifest(const std::filesystem::path& manifest_path,
                                    const std::filesystem::path& state_path,
                                    long long previous_update_id, int receiver_result) {
    auto manifest = load_json_or_default(manifest_path, nlohmann::json::object());
    const auto state = load_json_or_default(state_path, default_inbound_state());
    bool processed_new_update = false;
    bool saw_new_update = false;
    for (auto it = state.at("processed_updates").begin(); it != state.at("processed_updates").end(); ++it) {
        long long update_id = 0;
        try { update_id = std::stoll(it.key()); } catch (...) { continue; }
        if (update_id <= previous_update_id) continue;
        saw_new_update = true;
        if (it.value().value("status", std::string{}) == "PROCESSED") processed_new_update = true;
    }
    std::string status = manifest.value("telegram_receive_test_status", std::string{"NO_UPDATE_RECEIVED"});
    if (status == "NOT_REQUESTED") status = "NO_UPDATE_RECEIVED";
    if (processed_new_update && receiver_result == EXIT_SUCCESS) status = "RECEIVED_PROCESSED";
    else if (status == "RECEIVED_PROCESSED" && !saw_new_update && receiver_result == EXIT_SUCCESS) {
        // Preserve a previously proven update across subsequent empty polls in the same controlled run.
    } else if (receiver_result != EXIT_SUCCESS) {
        status = state.value("last_poll_status", std::string{}) == "UNAVAILABLE" ? "UNAVAILABLE" : "FAILED";
    } else if (saw_new_update) status = "FAILED";
    manifest["telegram_receive_test_status"] = status;
    manifest["telegram_last_update_id"] = state.value("last_update_id", 0LL);
    manifest["retry_summary"]["telegram_inbound_polls"] = state.value("poll_count", 0LL);
    if (status == "RECEIVED_PROCESSED" && manifest.value("run_status", std::string{}) == "L1_L2_L3_PASS")
        manifest["run_status"] = "STAGE1_CONTROLLED_ACCEPTANCE_PASS";
    if (status == "FAILED" || status == "UNAVAILABLE")
        manifest["error_summary"].push_back("telegram_inbound:" + status);
    manifest["end_time_utc"] = utc_now_iso();
    sync_system_status_artifact(manifest_path, manifest);
    write_json_atomic(manifest_path, manifest);
}

inline nlohmann::json default_inbound_state() {
    return {{"schema_version", 1}, {"last_update_id", 0},
            {"poll_count", 0}, {"last_poll_status", "NEVER_POLLED"},
            {"last_poll_at_epoch_ms", nullptr}, {"last_error", nullptr},
            {"processed_updates", nlohmann::json::object()}};
}

inline std::string command_reply(const std::string& text) {
    if (text == "/start" || text == "/help")
        return "ربات گزارش‌دهی فعال است.\nدستورها:\n/status وضعیت آخرین اجرا\n/last آخرین وضعیت پردازش\n/help راهنما";
    if (text == "/status")
        return "وضعیت معماری: Stage 1 در حال اعتبارسنجی است. تا تکمیل گیت‌ها هیچ سیگنال معاملاتی تأییدنشده‌ای ارسال نمی‌شود.";
    if (text == "/last")
        return "آخرین وضعیت معاملاتی معتبر: هنوز سیگنال کالیبره‌شده و دارای EV مثبت ثبت نشده است.";
    return {};
}

inline int run_inbound(const std::filesystem::path& state_path, const std::string& token,
                       const std::string& allowed_chat_id) {
    auto state = load_json_or_default(state_path, default_inbound_state());
    if (state.value("schema_version", 0) != 1 || !state.contains("processed_updates") ||
        !state.at("processed_updates").is_object())
        throw std::runtime_error("telegram_inbound_state_schema_invalid");
    const long long last_id = state.value("last_update_id", 0LL);
    const std::string endpoint = "https://api.telegram.org/bot" + token +
        "/getUpdates?offset=" + std::to_string(last_id + 1LL) + "&timeout=5";
    const auto response = perform_http(endpoint);
    if (response.transport != CURLE_OK || response.http_status != 200) {
        state["last_poll_status"] = "UNAVAILABLE";
        state["last_poll_at_epoch_ms"] = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        state["last_error"] = response.error;
        write_json_atomic(state_path, state);
        std::cerr << "TELEGRAM_INBOUND_UNAVAILABLE http=" << response.http_status
                  << " error=" << response.error << '\n';
        return EXIT_FAILURE;
    }
    state["poll_count"] = state.value("poll_count", 0LL) + 1LL;
    state["last_poll_status"] = "OK";
    state["last_poll_at_epoch_ms"] = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    state["last_error"] = nullptr;
    write_json_atomic(state_path, state);
    const auto parsed = nlohmann::json::parse(response.body);
    if (!parsed.value("ok", false) || !parsed.contains("result") || !parsed.at("result").is_array())
        throw std::runtime_error("telegram_getupdates_invalid_response");

    bool delivery_problem = false;
    for (const auto& update : parsed.at("result")) {
        if (!update.contains("update_id") || !update.at("update_id").is_number_integer()) continue;
        const auto update_id = update.at("update_id").get<long long>();
        const std::string key = std::to_string(update_id);
        if (state["processed_updates"].contains(key)) {
            auto& prior = state["processed_updates"][key];
            const auto status = prior.value("status", std::string{});
            if (reconcile_inbound_status(status) == "DELIVERY_UNKNOWN" && status == "REPLY_SENDING") {
                prior["status"] = "DELIVERY_UNKNOWN";
                prior["reply_error"] = "previous_process_ended_while_reply_sending";
                delivery_problem = true;
                write_json_atomic(state_path, state);
            } else if (status == "REPLY_PENDING") {
                prior["status"] = "REPLY_SENDING";
                write_json_atomic(state_path, state);
                const auto sent = send_message(token, allowed_chat_id, prior.value("reply_text", std::string{}));
                prior["reply_status"] = sent.status;
                prior["reply_message_id"] = sent.message_id > 0 ? nlohmann::json(sent.message_id) : nlohmann::json(nullptr);
                prior["status"] = sent.status == "DELIVERED" ? "PROCESSED" : sent.status;
                prior["reply_error"] = sent.detail;
                write_json_atomic(state_path, state);
                if (sent.status != "DELIVERED") delivery_problem = true;
            } else if (status == "DELIVERY_UNKNOWN" || status == "RETRYABLE_FAILURE" ||
                       status == "PERMANENT_FAILURE") {
                delivery_problem = true;
            }
            state["last_update_id"] = std::max(state.value("last_update_id", 0LL), update_id);
            write_json_atomic(state_path, state);
            continue;
        }

        auto& entry = state["processed_updates"][key];
        entry = {{"status", "RECEIVED"}, {"processed_at_epoch_ms",
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now().time_since_epoch()).count()}};
        std::string reply;
        nlohmann::json message = nullptr;
        if (update.contains("message") && update.at("message").is_object()) message = update.at("message");
        else if (update.contains("channel_post") && update.at("channel_post").is_object()) message = update.at("channel_post");
        if (message.is_object() && message.contains("chat") && message.at("chat").contains("id")) {
            const auto& chat = message.at("chat").at("id");
            const std::string chat_id = chat.is_string() ? chat.get<std::string>() : chat.dump();
            if (chat_id == allowed_chat_id && message.contains("text") && message.at("text").is_string()) {
                reply = command_reply(message.at("text").get<std::string>());
                if (reply.empty()) entry["status"] = "IGNORED_UNKNOWN_COMMAND";
            } else {
                entry["status"] = "IGNORED_UNAUTHORIZED_OR_NON_TEXT";
            }
        } else {
            entry["status"] = "IGNORED_NON_MESSAGE_UPDATE";
        }

        if (!reply.empty()) {
            entry["status"] = "REPLY_PENDING";
            entry["reply_text"] = reply;
            write_json_atomic(state_path, state);
            entry["status"] = "REPLY_SENDING";
            write_json_atomic(state_path, state);
            const auto sent = send_message(token, allowed_chat_id, reply);
            entry["reply_status"] = sent.status;
            entry["reply_message_id"] = sent.message_id > 0 ? nlohmann::json(sent.message_id) : nlohmann::json(nullptr);
            entry["reply_error"] = sent.detail;
            entry["status"] = sent.status == "DELIVERED" ? "PROCESSED" : sent.status;
            write_json_atomic(state_path, state);
            if (sent.status != "DELIVERED") delivery_problem = true;
        }
        state["last_update_id"] = std::max(state.value("last_update_id", 0LL), update_id);
        write_json_atomic(state_path, state);
    }
    std::cout << "TELEGRAM_INBOUND_LAST_UPDATE_ID=" << state.value("last_update_id", 0LL) << '\n';
    return delivery_problem ? EXIT_FAILURE : EXIT_SUCCESS;
}

} // namespace cfss::telegram
