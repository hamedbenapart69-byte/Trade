#include "cfss/lfs_v2.hpp"
#include "cfss/hash.hpp"
#include "cfss/okx_provider.hpp"

#include <algorithm>
#include <curl/curl.h>
#include <fstream>
#include <iterator>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

namespace {
std::string read_raw(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("lfs_hash_input_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}
json fetch_long_short(const std::string& instrument_id, std::int64_t decision_time_ms) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> end;
    std::int64_t previous_oldest = std::numeric_limits<std::int64_t>::max();
    const auto start_ms = decision_time_ms - 30LL * 86'400'000LL;
    for (int page = 0; page < 8; ++page) {
        std::string path = "/api/v5/rubik/stat/contracts/long-short-account-ratio-contract?instId=" +
                           cfss::okx::encode(instrument_id) + "&period=1H&limit=100";
        if (end) path += "&end=" + std::to_string(*end);
        const auto payload = cfss::okx::request(path);
        if (payload.at("data").empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload.at("data")) {
            if (!row.is_array() || row.size() < 2U) continue;
            const auto ts = cfss::okx::timestamp(row[0]);
            const auto ratio = cfss::okx::number(row[1]);
            if (ts <= 0 || !ratio || *ratio <= 0.0) continue;
            oldest = std::min(oldest, ts);
            if (ts >= start_ms) rows[ts] = {{"timestamp_ms", ts}, {"ratio", *ratio}};
        }
        if (oldest == std::numeric_limits<std::int64_t>::max() ||
            oldest >= previous_oldest || oldest <= start_ms) break;
        previous_oldest = oldest;
        end = oldest - 1;
        std::this_thread::sleep_for(std::chrono::milliseconds(250));
    }
    json out = json::array();
    for (const auto& [ts, row] : rows) {
        (void)ts;
        out.push_back(row);
    }
    return out;
}

std::int64_t latest_ts(const json& rows) {
    if (!rows.is_array() || rows.empty()) return 0;
    return cfss::okx::timestamp(rows.back().value("timestamp_ms", json{}));
}

json component_json(const cfss::lfs::V2Component& c) {
    return {
        {"id", c.id}, {"score", c.score ? json(*c.score) : json(nullptr)},
        {"data_class", c.data_class}, {"available_at_ms", c.available_at_ms},
        {"definition_id", c.definition_id}, {"reason", c.reason}
    };
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: lfs_v2_probe <l1-json> <output-json>\n";
        return 2;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "curl_global_init_failed\n";
        return 1;
    }
    try {
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("l1_input_open_failed");
        const json l1 = json::parse(input);
        if (!l1.is_object() || !l1.contains("instruments") || !l1.at("instruments").is_array())
            throw std::runtime_error("l1_instruments_missing");

        if (!l1.contains("window") || !l1.at("window").contains("end_ms"))
            throw std::runtime_error("l1_decision_time_missing");
        const auto decision_time = l1.at("window").at("end_ms").get<std::int64_t>();
        const auto l1_hash = cfss::sha256_hex(read_raw(argv[1]));
        json instruments = json::array();
        std::size_t calculated_count = 0U;
        for (const auto& instrument : l1.at("instruments")) {
            const auto id = instrument.value("instrument_id", std::string{});
            const auto symbol = instrument.value("unified_symbol", std::string{"UNKNOWN"});
            if (id.empty()) throw std::runtime_error("instrument_id_missing");
            const json long_short = fetch_long_short(id, decision_time);

            const auto candles = cfss::lfs::filter_time_series(instrument.value("candles", json::array()), decision_time);
            const auto funding = cfss::lfs::filter_time_series(instrument.value("funding", json::array()), decision_time);
            const auto oi = cfss::lfs::filter_time_series(instrument.value("open_interest", json::array()), decision_time);
            const auto long_short_as_json = cfss::lfs::filter_time_series(long_short, decision_time);
            const auto lfs1 = cfss::lfs::lfs1_proxy_score(candles);
            const auto lfs2 = cfss::lfs::funding_extreme_score(funding);
            const auto lfs3 = cfss::lfs::long_short_extreme_score(long_short_as_json);
            const auto lfs4 = cfss::lfs::bb_width_compression_score(candles);
            const auto lfs5 = cfss::lfs::oi_change_score(oi);

            const std::array<cfss::lfs::V2Component, 5> components{{
                {"LFS1_BOOK_THINNESS", lfs1, "PROXY", latest_ts(candles), "lfs1_atr_volume_percentile_v2",
                 "OHLCV proxy only; no REAL order-book depth history is present"},
                {"LFS2_FUNDING_EXTREME", lfs2, "REAL", latest_ts(funding), "lfs2_abs_funding_percentile_v2",
                 "Absolute funding-rate percentile over available 30-day REAL history"},
                {"LFS3_LONG_SHORT_POSITIONING", lfs3, "REAL", latest_ts(long_short), "lfs3_abs_log_ratio_percentile_v2",
                 "OKX contract long/short account ratio; 30-day REAL history"},
                {"LFS4_VOLATILITY_COMPRESSION", lfs4, "REAL", latest_ts(candles), "lfs4_bb_width_percentile_v2",
                 "20-period Bollinger width inverse percentile over 90-day REAL OHLCV history"},
                {"LFS5_OPEN_INTEREST_CHANGE", lfs5, "REAL", latest_ts(oi), "lfs5_abs_24h_oi_change_percentile_v2",
                 "Absolute 24-hour OI change percentile over available REAL OI history"}
            }};
            const auto result = cfss::lfs::aggregate_v2(components, decision_time);

            if (result.status == "CALCULATED") ++calculated_count;
            json component_rows = json::array();
            for (const auto& c : components) component_rows.push_back(component_json(c));
            instruments.push_back({
                {"instrument_id", id}, {"symbol", symbol},
                {"status", result.status},
                {"score", result.score ? json(*result.score) : json(nullptr)},
                {"data_class", result.data_class},
                {"component_coverage", {{"available_scores", 5U - result.missing_count}, {"required_scores", 5}}},
                {"components", component_rows},
                {"long_short_rows", long_short_as_json.size()},
                {"long_short_scope", "OKX contract-level all-trader account ratio"}
            });
        }

        const json output = {
            {"schema_version", "1.0.0"}, {"artifact_type", "cfss_lfs_v2_proxy"},
            {"version", "LFS_V2_PROXY"},
            {"source_run_id", l1.value("run_id", std::string{"UNKNOWN"})},
            {"source_scan_id", l1.value("scan_id", std::string{"UNKNOWN"})},
            {"decision_time_ms", decision_time},
            {"l1_sha256", l1_hash},
            {"status", calculated_count == instruments.size() ? "CALCULATED" : (calculated_count == 0U ? "UNAVAILABLE" : "PARTIAL")},
            {"note", "Research feature score only. PROXY is not REAL and is not an actionable trade signal."},
            {"instruments", instruments}
        };
        std::ofstream out(argv[2], std::ios::trunc);
        if (!out) throw std::runtime_error("lfs_output_open_failed");
        out << output.dump(2) << '\n';
        if (!out.good()) throw std::runtime_error("lfs_output_write_failed");
        std::cout << "LFS_V2_INSTRUMENTS=" << instruments.size() << '\n';
        for (const auto& item : instruments) {
            std::cout << item.at("symbol").get<std::string>() << " LFS_V2_STATUS="
                      << item.at("status").get<std::string>() << " DATA_CLASS="
                      << item.at("data_class").get<std::string>() << '\n';
        }
        curl_global_cleanup();
        return 0;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "LFS_V2_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
