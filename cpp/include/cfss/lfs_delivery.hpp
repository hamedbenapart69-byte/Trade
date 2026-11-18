#pragma once

#include "cfss/hash.hpp"
#include <nlohmann/json.hpp>
#include <string>

namespace cfss::lfs_delivery {
using json = nlohmann::json;

inline std::string report_id(const json& report) {
    return sha256_hex(report.dump(-1, ' ', false, json::error_handler_t::strict));
}

inline std::string message_text(const json& report) {
    std::string message = "گزارش مرحلهٔ ۲ سامانهٔ معاملات\n";
    message += "نسخه: LFS_V2_PROXY\n";
    message += "وضعیت: تحقیقاتی، NOT_CALIBRATED\n";
    message += "این امتیاز سیگنال معاملاتی نیست و هیچ سفارشی اجرا نمی‌شود.\n\n";
    if (report.contains("instruments") && report.at("instruments").is_array()) {
        for (const auto& item : report.at("instruments")) {
            message += item.value("symbol", std::string{"UNKNOWN"});
            message += " | وضعیت: " + item.value("status", std::string{"UNAVAILABLE"});
            message += " | طبقه: " + item.value("data_class", std::string{"UNAVAILABLE"});
            if (item.contains("score") && item.at("score").is_number()) {
                message += " | LFS: " + item.at("score").dump();
            } else {
                message += " | LFS: UNAVAILABLE";
            }
            const auto coverage = item.value("component_coverage", json::object());
            message += " | پوشش: " + std::to_string(coverage.value("available_scores", 0)) + "/5\n";
        }
    }
    message += "\nLFS1 در این نسخه PROXY است؛ خروجی تا پایان اعتبارسنجی صرفاً پژوهشی است.";
    return message;
}

inline bool already_delivered(const json& outbox, const std::string& id) {
    if (!outbox.is_object() || !outbox.contains("receipts") || !outbox.at("receipts").is_array()) return false;
    for (const auto& receipt : outbox.at("receipts")) {
        if (receipt.value("report_id", std::string{}) == id &&
            (receipt.value("status", std::string{}) == "DELIVERED" ||
             receipt.value("status", std::string{}) == "SENDING" ||
             receipt.value("status", std::string{}) == "DELIVERY_UNKNOWN")) return true;
    }
    return false;
}

} // namespace cfss::lfs_delivery
