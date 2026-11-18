#pragma once

#include <cmath>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace cfss::nss {

inline nlohmann::json build_basis_series(const nlohmann::json& perpetual_candles,
                                         const nlohmann::json& spot_candles,
                                         std::int64_t decision_time_ms) {
    using json = nlohmann::json;
    std::map<std::int64_t, double> spot_close;
    if (!spot_candles.is_array() || !perpetual_candles.is_array()) return json::array();
    for (const auto& row : spot_candles) {
        if (!row.is_object() || !row.contains("timestamp_ms") || !row.at("timestamp_ms").is_number_integer() ||
            !row.contains("close") || !row.at("close").is_number()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        const double close = row.at("close").get<double>();
        if (ts > 0 && ts <= decision_time_ms && std::isfinite(close) && close > 0.0)
            spot_close[ts] = close;
    }
    json out = json::array();
    for (const auto& row : perpetual_candles) {
        if (!row.is_object() || !row.contains("timestamp_ms") || !row.at("timestamp_ms").is_number_integer() ||
            !row.contains("close") || !row.at("close").is_number()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        const double perp = row.at("close").get<double>();
        if (ts <= 0 || ts > decision_time_ms || !std::isfinite(perp) || perp <= 0.0) continue;
        const auto spot = spot_close.find(ts);
        if (spot == spot_close.end()) continue;
        const double basis_bps = (perp / spot->second - 1.0) * 10000.0;
        if (!std::isfinite(basis_bps)) continue;
        out.push_back({
            {"timestamp_ms", ts},
            {"basis_bps", basis_bps},
            {"perpetual_close", perp},
            {"spot_close", spot->second},
            {"source_quality", "REAL"},
            {"definition_id", "OKX_SPOT_PERP_CLOSE_BASIS_BPS_V1"}
        });
    }
    return out;
}

} // namespace cfss::nss
