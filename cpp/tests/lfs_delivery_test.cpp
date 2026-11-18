#include "cfss/lfs_delivery.hpp"
#include <cstdlib>
#include <iostream>

int main() {
    const nlohmann::json report = {
        {"artifact_type", "cfss_lfs_v2_proxy"},
        {"source_scan_id", "scan-test"},
        {"instruments", nlohmann::json::array({
            {{"symbol", "BTC/USDT:USDT"}, {"status", "CALCULATED"},
             {"data_class", "PROXY"}, {"score", 0.75},
             {"component_coverage", {{"available_scores", 5}}}}
        })}
    };
    const auto id1 = cfss::lfs_delivery::report_id(report);
    const auto id2 = cfss::lfs_delivery::report_id(report);
    if (id1.empty() || id1 != id2) return 1;

    const auto message = cfss::lfs_delivery::message_text(report);
    if (message.find("PROXY") == std::string::npos ||
        message.find("سیگنال معاملاتی نیست") == std::string::npos) return 2;

    const nlohmann::json delivered = {
        {"receipts", nlohmann::json::array({
            {{"report_id", id1}, {"status", "DELIVERED"}}
        })}
    };
    if (!cfss::lfs_delivery::already_delivered(delivered, id1)) return 3;

    std::cout << "LFS_TELEGRAM_DELIVERY_CONTRACT_PASS\n";
    return 0;
}
