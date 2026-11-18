#include "cfss/okx_provider.hpp"
#include "cfss/nss_basis.hpp"
#include "cfss/atomic_file.hpp"

#include <curl/curl.h>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

namespace {
json fetch_spot_candles(const std::string& instrument_id,
                        std::int64_t start_ms, std::int64_t end_ms) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < 20; ++page) {
        std::string path = "/api/v5/market/history-candles?instId=" +
                           cfss::okx::encode(instrument_id) + "&bar=1H&limit=300";
        if (after) path += "&after=" + std::to_string(*after);
        const auto payload = cfss::okx::request(path);
        const auto retrieved = cfss::okx::utc_iso(cfss::okx::now_ms());
        if (payload.at("data").empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload.at("data")) {
            if (!row.is_array() || row.size() < 9U) continue;
            const auto ts = cfss::okx::timestamp(row[0]);
            const auto close = cfss::okx::number(row[4]);
            const auto confirmed = cfss::okx::text(json{{"v", row[8]}}, "v") == "1";
            if (ts <= 0) continue;
            oldest = std::min(oldest, ts);
            if (ts < start_ms || ts >= end_ms || ts % 3'600'000LL != 0 ||
                ts + 3'600'000LL > end_ms || !confirmed || !close || *close <= 0.0) continue;
            rows[ts] = {
                {"timestamp_ms", ts}, {"close", *close},
                {"retrieved_at_utc", retrieved}
            };
        }
        if (oldest == std::numeric_limits<std::int64_t>::max() ||
            oldest >= previous_oldest || oldest <= start_ms) break;
        previous_oldest = oldest;
        after = oldest;
        std::this_thread::sleep_for(std::chrono::milliseconds(120));
    }
    json out = json::array();
    for (const auto& [ts, row] : rows) { (void)ts; out.push_back(row); }
    return out;
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: nss_basis_collector <l1-market-data.json> <nss-basis.json>\n";
        return 2;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    try {
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("l1_input_open_failed");
        const json l1 = json::parse(input);
        if (!l1.is_object() || !l1.contains("instruments") || !l1.at("instruments").is_array() ||
            !l1.contains("window") || !l1.at("window").contains("end_ms"))
            throw std::runtime_error("l1_contract_invalid");
        const auto decision_time = l1.at("window").at("end_ms").get<std::int64_t>();
        const auto start_time = decision_time - 90LL * 86'400'000LL;
        json instruments = json::array();
        for (const auto& item : l1.at("instruments")) {
            const auto base = item.value("base", std::string{});
            const auto symbol = item.value("unified_symbol", std::string{"UNKNOWN"});
            if (base.empty()) throw std::runtime_error("instrument_base_missing");
            json spot;
            std::string error;
            try {
                spot = fetch_spot_candles(base + "-USDT", start_time, decision_time);
            } catch (const std::exception& e) {
                error = e.what();
                spot = json::array();
            }
            const auto perp = item.value("candles", json::array());
            const auto basis = cfss::nss::build_basis_series(perp, spot, decision_time);
            instruments.push_back({
                {"symbol", symbol},
                {"spot_instrument_id", base + "-USDT"},
                {"perpetual_instrument_id", item.value("instrument_id", std::string{})},
                {"source_quality", basis.empty() ? "UNAVAILABLE" : "REAL"},
                {"definition_id", "OKX_SPOT_PERP_CLOSE_BASIS_BPS_V1"},
                {"status", basis.size() >= 24U * 20U ? "AVAILABLE" : "PARTIAL"},
                {"basis_rows", basis.size()},
                {"spot_rows", spot.size()},
                {"basis", basis},
                {"error", error.empty() ? json(nullptr) : json(error)}
            });
        }
        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_nss_basis_v1"},
            {"source_run_id", l1.value("run_id", std::string{"UNKNOWN"})},
            {"source_scan_id", l1.value("scan_id", std::string{"UNKNOWN"})},
            {"decision_time_ms", decision_time},
            {"window_days", 90},
            {"instruments", instruments}
        };
        cfss::write_file_atomic(argv[2], output.dump(2) + "\n", true);
        for (const auto& item : instruments)
            std::cout << item.at("symbol").get<std::string>()
                      << " NSS_BASIS_STATUS=" << item.at("status").get<std::string>()
                      << " rows=" << item.at("basis_rows").get<std::size_t>() << '\n';
        curl_global_cleanup();
        return 0;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "NSS_BASIS_COLLECTOR_ERROR=" << error.what() << '\n';
        return 1;
    }
}
