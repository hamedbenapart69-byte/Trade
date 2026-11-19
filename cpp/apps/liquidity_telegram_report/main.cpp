#include "cfss/telegram_l3.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"

#include <curl/curl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstdlib>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {
json read_json(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("input_open_failed");
    auto value = json::parse(in);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid");
    return value;
}

void persist(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", false);
}

json load_outbox(const std::filesystem::path& path) {
    if (!std::filesystem::exists(path))
        return {{"schema_version", "1.0.0"}, {"receipts", json::array()}};
    auto value = read_json(path);
    if (!value.contains("receipts") || !value.at("receipts").is_array())
        throw std::runtime_error("outbox_schema_invalid");
    return value;
}

json* find_receipt(json& outbox, const std::string& id) {
    for (auto& item : outbox["receipts"])
        if (item.value("report_id", std::string{}) == id) return &item;
    return nullptr;
}

std::string report_id(const json& report) {
    return cfss::sha256_hex(report.dump());
}

std::string report_text(const json& report) {
    std::string out = "گزارش فنی مرحله ۴ | Liquidity Zones + Market Phase\n";
    out += "تحلیل ساختاری؛ نه سیگنال و نه دستور معامله.\n";
    out += "نسخه: LIQUIDITY_PHASE_V1 | ورودی: OHLCV واقعی | روش: RULE_BASED_PROXY\n";
    out += "شناسه اجرا: " + report.value("source_run_id", std::string{"UNKNOWN"}) + "\n\n";
    if (!report.contains("instruments") || !report.at("instruments").is_array())
        throw std::runtime_error("instrument_array_missing");
    for (const auto& item : report.at("instruments")) {
        out += item.value("symbol", std::string{"UNKNOWN"}) + "\n";
        out += "فاز: " + item.value("phase", std::string{"UNAVAILABLE"}) +
               " | قیمت مرجع: " + item.value("current_price", json(nullptr)).dump() + "\n";
        out += "علت فاز: " + item.value("phase_reason", std::string{"UNSPECIFIED"}) + "\n";
        for (const auto* key : {"nearest_support", "nearest_resistance"}) {
            if (!item.contains(key) || !item.at(key).is_object()) continue;
            const auto& zone = item.at(key);
            out += (std::string{key} == "nearest_support" ? "حمایت نزدیک: " : "مقاومت نزدیک: ");
            out += zone.at("low").dump() + " تا " + zone.at("high").dump() +
                   " | فاصله: " + zone.at("distance_from_price").dump() + "\n";
        }
        std::vector<json> active;
        if (item.contains("zones") && item.at("zones").is_array()) {
            for (const auto& zone : item.at("zones"))
                if (zone.value("status", std::string{}) == "ACTIVE") active.push_back(zone);
        }
        std::sort(active.begin(), active.end(), [&](const json& a, const json& b) {
            const double da = std::abs(item.at("current_price").get<double>() -
                (a.at("low").get<double>() + a.at("high").get<double>()) / 2.0);
            const double db = std::abs(item.at("current_price").get<double>() -
                (b.at("low").get<double>() + b.at("high").get<double>()) / 2.0);
            return da < db;
        });
        out += "سطوح فعال نزدیک:\n";
        const auto count = std::min<std::size_t>(3U, active.size());
        for (std::size_t i = 0U; i < count; ++i) {
            const auto& zone = active[i];
            out += "- " + zone.value("side", std::string{"UNKNOWN"}) + " " +
                   zone.at("low").dump() + "-" + zone.at("high").dump() +
                   " | wick=" + zone.at("wick_ratio").dump() +
                   " | volume=" + zone.at("volume_ratio").dump() +
                   " | touches=" + std::to_string(zone.value("touch_count", 0U)) + "\n";
        }
        out += "\n";
    }
    out += "سطوح پس از بسته‌شدن دو کندل تأییدکننده منتشر می‌شوند؛ سطوح تأییدشده بازنویسی نمی‌شوند.\n";
    out += "این مدل قانون‌محور است و اعتبار سودآوری آن اثبات نشده است.";
    return out;
}

int prepare(const json& report, const std::filesystem::path& path) {
    auto outbox = load_outbox(path);
    const auto id = report_id(report);
    if (auto* receipt = find_receipt(outbox, id)) {
        const auto status = receipt->value("status", std::string{});
        if (status == "SENDING") {
            (*receipt)["status"] = "DELIVERY_UNKNOWN";
            (*receipt)["reason"] = "process_restarted_during_send; replay_blocked";
            persist(path, outbox);
            std::cout << "LIQUIDITY_TELEGRAM_REPLAY_BLOCKED=DELIVERY_UNKNOWN\n";
            return 0;
        }
        if (status == "DELIVERED" || status == "DELIVERY_UNKNOWN" ||
            status == "PERMANENT_FAILURE") {
            std::cout << "LIQUIDITY_TELEGRAM_REPLAY_BLOCKED=" << status << '\n';
            return 0;
        }
        if (status == "RESERVED") {
            std::cout << "LIQUIDITY_TELEGRAM_ALREADY_RESERVED\n";
            return 0;
        }
        throw std::runtime_error("outbox_status_invalid");
    }
    outbox["receipts"].push_back({
        {"report_id", id}, {"status", "RESERVED"}, {"attempts", 0},
        {"http_status", nullptr}, {"message_id", nullptr},
        {"created_at_utc", cfss::telegram::utc_now_iso()}
    });
    persist(path, outbox);
    std::cout << "LIQUIDITY_TELEGRAM_RESERVED report_id=" << id << '\n';
    return 0;
}

int send(const json& report, const std::filesystem::path& path) {
    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    if (!token || !chat_id || token[0] == '\0' || chat_id[0] == '\0')
        throw std::runtime_error("TELEGRAM_CONFIGURATION_MISSING");
    auto outbox = load_outbox(path);
    const auto id = report_id(report);
    auto* receipt = find_receipt(outbox, id);
    if (!receipt) throw std::runtime_error("report_not_reserved");
    const auto status = receipt->value("status", std::string{});
    if (status == "DELIVERED" || status == "DELIVERY_UNKNOWN" ||
        status == "PERMANENT_FAILURE") {
        std::cout << "LIQUIDITY_TELEGRAM_SEND_BLOCKED=" << status << '\n';
        return status == "DELIVERED" ? 0 : 1;
    }
    if (status != "RESERVED") throw std::runtime_error("report_not_sendable");
    (*receipt)["status"] = "SENDING";
    (*receipt)["attempts"] = receipt->value("attempts", 0) + 1;
    (*receipt)["send_started_at_utc"] = cfss::telegram::utc_now_iso();
    persist(path, outbox);

    const auto result = cfss::telegram::send_message(token, chat_id, report_text(report));
    (*receipt)["status"] = result.status;
    (*receipt)["http_status"] = result.http_status;
    (*receipt)["message_id"] = result.message_id > 0 ? json(result.message_id) : json(nullptr);
    (*receipt)["detail"] = result.detail.empty() ? json(nullptr) : json(result.detail);
    (*receipt)["completed_at_utc"] = cfss::telegram::utc_now_iso();
    persist(path, outbox);
    std::cout << "LIQUIDITY_TELEGRAM_STATUS=" << result.status
              << " HTTP=" << result.http_status
              << " MESSAGE_ID=" << result.message_id << '\n';
    return result.status == "DELIVERED" ? 0 : 1;
}
}

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: liquidity_telegram_report <prepare|send> <report.json> <outbox.json>\n";
        return 2;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    try {
        const std::string mode{argv[1]};
        const auto report = read_json(argv[2]);
        if (report.value("artifact_type", std::string{}) != "cfss_liquidity_phase_v1")
            throw std::runtime_error("liquidity_report_type_invalid");
        int result = EXIT_FAILURE;
        if (mode == "--prepare") result = prepare(report, argv[3]);
        else if (mode == "--send") result = send(report, argv[3]);
        else throw std::runtime_error("unknown_mode");
        curl_global_cleanup();
        return result;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "LIQUIDITY_TELEGRAM_ERROR=" << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
