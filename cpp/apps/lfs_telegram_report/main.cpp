#include "cfss/lfs_delivery.hpp"
#include "cfss/okx_provider.hpp"
#include "cfss/signal.hpp"

#include <curl/curl.h>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

namespace {
void write_atomic(const std::filesystem::path& path, const json& value) {
    if (!path.parent_path().empty()) std::filesystem::create_directories(path.parent_path());
    auto temp = path;
    temp += ".tmp";
    {
        std::ofstream out(temp, std::ios::trunc);
        if (!out) throw std::runtime_error("outbox_temp_open_failed");
        out << value.dump(2) << '\n';
        if (!out.good()) throw std::runtime_error("outbox_temp_write_failed");
    }
    std::filesystem::rename(temp, path);
}

json load_outbox(const std::filesystem::path& path) {
    if (!std::filesystem::exists(path)) return {
        {"schema_version", "1.0.0"},
        {"receipts", json::array()}
    };
    std::ifstream in(path);
    if (!in) throw std::runtime_error("outbox_open_failed");
    auto outbox = json::parse(in);
    if (!outbox.is_object() || !outbox.contains("receipts") || !outbox.at("receipts").is_array())
        throw std::runtime_error("outbox_schema_invalid");
    return outbox;
}

json* find_receipt(json& outbox, const std::string& report_id) {
    for (auto& receipt : outbox["receipts"]) {
        if (receipt.value("report_id", std::string{}) == report_id) return &receipt;
    }
    return nullptr;
}

int prepare(const json& report, const std::filesystem::path& path) {
    json outbox = load_outbox(path);
    const auto id = cfss::lfs_delivery::report_id(report);
    if (auto* existing = find_receipt(outbox, id)) {
        const auto status = existing->value("status", std::string{});
        if (status == "DELIVERED" || status == "DELIVERY_UNKNOWN") {
            std::cout << "TELEGRAM_REPORT_SEND_BLOCKED status=" << status << '\n';
            return 0;
        }
        if (status == "SENDING") {
            (*existing)["status"] = "DELIVERY_UNKNOWN";
            (*existing)["reason"] = "stale_reserved_attempt; duplicate_send_blocked";
            write_atomic(path, outbox);
            std::cout << "TELEGRAM_REPORT_SEND_BLOCKED status=DELIVERY_UNKNOWN\n";
            return 0;
        }
    }
    outbox["receipts"].push_back({
        {"report_id", id}, {"status", "SENDING"}, {"attempts", 1},
        {"started_at_utc", cfss::okx::utc_iso(cfss::okx::now_ms())}
    });
    write_atomic(path, outbox);
    std::cout << "TELEGRAM_REPORT_RESERVED report_id=" << id << '\n';
    return 0;
}

int send(const json& report, const std::filesystem::path& path) {
    const char* token_env = std::getenv("TELEGRAM_TOKEN");
    const char* chat_env = std::getenv("TELEGRAM_CHAT_ID");
    if (!token_env || !chat_env || std::string(token_env).empty() || std::string(chat_env).empty()) {
        std::cerr << "TELEGRAM_CONFIGURATION_MISSING\n";
        return 2;
    }

    json outbox = load_outbox(path);
    const auto id = cfss::lfs_delivery::report_id(report);
    auto* receipt = find_receipt(outbox, id);
    if (!receipt) throw std::runtime_error("telegram_send_without_reserved_outbox");
    const auto status = receipt->value("status", std::string{});
    if (status != "SENDING") {
        std::cout << "TELEGRAM_REPORT_SEND_SKIPPED status=" << status << '\n';
        return 0;
    }

    std::string response_text;
    const bool sent = cfss::send_telegram_message(
        token_env, chat_env, cfss::lfs_delivery::message_text(report), &response_text, false);
    json response = json::object();
    try { response = json::parse(response_text); } catch (...) {}
    if (sent && response.value("ok", false) && response.contains("result") &&
        response["result"].contains("message_id")) {
        (*receipt)["status"] = "DELIVERED";
        (*receipt)["message_id"] = response["result"]["message_id"];
        (*receipt)["delivered_at_utc"] = cfss::okx::utc_iso(cfss::okx::now_ms());
        write_atomic(path, outbox);
        std::cout << "TELEGRAM_REPORT_DELIVERED report_id=" << id
                  << " message_id=" << response["result"]["message_id"] << '\n';
        return 0;
    }

    (*receipt)["status"] = "DELIVERY_UNKNOWN";
    (*receipt)["reason"] = "telegram_response_not_confirmed; duplicate_send_blocked";
    write_atomic(path, outbox);
    std::cerr << "TELEGRAM_DELIVERY_UNKNOWN_DUPLICATE_BLOCKED\n";
    return 3;
}
}

int main(int argc, char** argv) {
    if (argc != 4 || (std::string(argv[1]) != "--prepare" && std::string(argv[1]) != "--send")) {
        std::cerr << "usage: lfs_telegram_report <--prepare|--send> <lfs-v2-json> <outbox-json>\n";
        return 2;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "curl_global_init_failed\n";
        return 1;
    }
    try {
        std::ifstream input(argv[2]);
        if (!input) throw std::runtime_error("lfs_report_open_failed");
        const json report = json::parse(input);
        if (report.value("artifact_type", std::string{}) != "cfss_lfs_v2_proxy")
            throw std::runtime_error("lfs_report_artifact_type_invalid");

        const std::filesystem::path outbox_path(argv[3]);
        const int result = std::string(argv[1]) == "--prepare"
            ? prepare(report, outbox_path)
            : send(report, outbox_path);
        curl_global_cleanup();
        return result;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "LFS_TELEGRAM_REPORT_ERROR=" << error.what() << '\n';
        return 1;
    }
}
