#include "cfss/telegram_l3.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include <curl/curl.h>
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
    std::string out = "گزارش مرحله ۶ | فراشناخت، کالیبراسیون و EV\n";
    out += "این گزارش تصمیم‌یار پژوهشی است؛ هیچ سفارش یا اجرای معاملاتی ندارد.\n";
    out += "شناسه اجرا: " + report.value("source_run_id", std::string{"UNKNOWN"}) + "\n";
    out += "وضعیت دفتر نتایج: " + report.value("outcome_ledger_status", std::string{"UNKNOWN"}) +
           " | تعداد نتایج بسته‌شده: " + std::to_string(report.value("outcome_ledger_count", 0)) + "\n";
    for (const auto& item : report.at("instruments")) {
        out += "\n" + item.value("symbol", std::string{"UNKNOWN"}) + "\n";
        for (const auto* key : {"lrt", "nmt"}) {
            const auto& engine = item.at(key);
            out += std::string(key == std::string("lrt") ? "LRT" : "NMT");
            out += " | وضعیت: " + engine.value("candidate_status", std::string{"UNKNOWN"});
            out += " | اطمینان: " + engine.value("confidence_status", std::string{"NOT_CALIBRATED"});
            out += " | EV: " + engine.value("ev_status", std::string{"NOT_CALCULATED"}) + "\n";
            out += "علت: " + engine.value("reason", std::string{"UNSPECIFIED"}) + "\n";
        }
    }
    out += "\nتا زمانی که داده نتیجه معتبر و کافی وجود نداشته باشد، احتمال برد و EV عددی منتشر نمی‌شود.";
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
            std::cout << "META_COGNITION_TELEGRAM_REPLAY_BLOCKED=DELIVERY_UNKNOWN\n";
            return 0;
        }
        if (status == "DELIVERED" || status == "DELIVERY_UNKNOWN" || status == "PERMANENT_FAILURE") {
            std::cout << "META_COGNITION_TELEGRAM_REPLAY_BLOCKED=" << status << '\n';
            return status == "DELIVERED" ? 0 : 1;
        }
        if (status == "RESERVED") return 0;
        throw std::runtime_error("outbox_status_invalid");
    }
    outbox["receipts"].push_back({
        {"report_id", id}, {"status", "RESERVED"}, {"attempts", 0},
        {"http_status", nullptr}, {"message_id", nullptr},
        {"created_at_utc", cfss::telegram::utc_now_iso()}
    });
    persist(path, outbox);
    std::cout << "META_COGNITION_TELEGRAM_RESERVED report_id=" << id << '\n';
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
    if (status == "DELIVERED" || status == "DELIVERY_UNKNOWN" || status == "PERMANENT_FAILURE")
        return status == "DELIVERED" ? 0 : 1;
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
    std::cout << "META_COGNITION_TELEGRAM_STATUS=" << result.status
              << " HTTP=" << result.http_status
              << " MESSAGE_ID=" << result.message_id << '\n';
    return result.status == "DELIVERED" ? 0 : 1;
}
}
int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: meta_cognition_telegram_report <prepare|send> <report.json> <outbox.json>\n";
        return 2;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    try {
        const std::string mode{argv[1]};
        const auto report = read_json(argv[2]);
        if (report.value("artifact_type", std::string{}) != "cfss_meta_cognition_v1")
            throw std::runtime_error("meta_cognition_report_type_invalid");
        int result = EXIT_FAILURE;
        if (mode == "--prepare") result = prepare(report, argv[3]);
        else if (mode == "--send") result = send(report, argv[3]);
        else throw std::runtime_error("unknown_mode");
        curl_global_cleanup();
        return result;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "META_COGNITION_TELEGRAM_ERROR=" << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
