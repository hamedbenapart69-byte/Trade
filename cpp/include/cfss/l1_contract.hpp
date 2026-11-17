#pragma once
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>

namespace cfss {
inline void require_string(const nlohmann::json& object, const char* key) {
    if (!object.contains(key) || !object.at(key).is_string() || object.at(key).get<std::string>().empty())
        throw std::invalid_argument(std::string("contract_field_invalid:") + key);
}
inline double require_finite_number(const nlohmann::json& value, std::string_view field,
                                    bool positive = false, bool non_negative = false) {
    if (!value.is_number()) throw std::invalid_argument("contract_numeric_field_invalid:" + std::string(field));
    const double number = value.get<double>();
    if (!std::isfinite(number) || (positive && number <= 0.0) || (non_negative && number < 0.0))
        throw std::invalid_argument("contract_numeric_field_out_of_range:" + std::string(field));
    return number;
}
inline void validate_nullable_number(const nlohmann::json& value, std::string_view field,
                                     bool positive = false) {
    if (!value.is_null()) (void)require_finite_number(value, field, positive);
}
inline void validate_time_series(const nlohmann::json& rows, const char* field, std::int64_t now_ms) {
    if (!rows.is_array()) throw std::invalid_argument(std::string("contract_series_not_array:") + field);
    std::int64_t previous = 0;
    for (const auto& row : rows) {
        if (!row.is_object() || !row.contains("timestamp_ms") || !row.at("timestamp_ms").is_number_integer())
            throw std::invalid_argument(std::string("contract_timestamp_invalid:") + field);
        const auto timestamp = row.at("timestamp_ms").get<std::int64_t>();
        if (timestamp <= previous || timestamp <= 0)
            throw std::invalid_argument(std::string("contract_timestamp_not_strictly_increasing:") + field);
        if (timestamp > now_ms)
            throw std::invalid_argument(std::string("contract_future_timestamp:") + field);
        previous = timestamp;
    }
}
inline nlohmann::json build_l2_artifact(const nlohmann::json& contract, std::int64_t now_ms) {
    if (!contract.is_object() || !contract.contains("schema_version") || contract.at("schema_version") != "1.0.0")
        throw std::invalid_argument("unsupported_l1_contract_schema_version");
    require_string(contract, "run_id");
    require_string(contract, "scan_id");
    require_string(contract, "acquired_at_utc");
    if (!contract.contains("window") || !contract.at("window").is_object() ||
        contract.at("window").value("timeframe", std::string{}) != "1h" ||
        !contract.at("window").contains("start_ms") || !contract.at("window").at("start_ms").is_number_integer() ||
        !contract.at("window").contains("end_ms") || !contract.at("window").at("end_ms").is_number_integer())
        throw std::invalid_argument("contract_window_invalid");
    const auto window_start = contract.at("window").at("start_ms").get<std::int64_t>();
    const auto window_end = contract.at("window").at("end_ms").get<std::int64_t>();
    if (window_start <= 0 || window_end < window_start || window_end > now_ms)
        throw std::invalid_argument("contract_window_out_of_range");
    if (!contract.contains("provider") || !contract.at("provider").is_object())
        throw std::invalid_argument("contract_provider_missing");
    require_string(contract.at("provider"), "primary_provider_id");
    if (!contract.contains("instruments") || !contract.at("instruments").is_array() || contract.at("instruments").empty())
        throw std::invalid_argument("contract_instruments_missing");
    nlohmann::json artifact = {
        {"artifact_type", "cfss_l2_status_v1"}, {"source_schema_version", "1.0.0"},
        {"source_run_id", contract.at("run_id")}, {"source_scan_id", contract.at("scan_id")},
        {"created_at_epoch_ms", now_ms},
        {"instruments", nlohmann::json::array()}
    };
    std::unordered_set<std::string> seen_instrument_ids;
    std::unordered_set<std::string> seen_symbols;
    for (const auto& instrument : contract.at("instruments")) {
        for (const char* key : {"instrument_id", "unified_symbol", "base", "quote", "settle",
                                "contract_type", "provider_id", "timeframe"}) require_string(instrument, key);
        if (instrument.at("contract_type") != "linear_perpetual" ||
            instrument.at("quote") != "USDT" || instrument.at("settle") != "USDT")
            throw std::invalid_argument("instrument_contract_identity_not_supported");
        if (!seen_instrument_ids.insert(instrument.at("instrument_id").get<std::string>()).second ||
            !seen_symbols.insert(instrument.at("unified_symbol").get<std::string>()).second)
            throw std::invalid_argument("duplicate_instrument_identity");
        if (instrument.contains("contract_size") && !instrument.at("contract_size").is_null())
            (void)require_finite_number(instrument.at("contract_size"), "contract_size", true);
        if (instrument.at("timeframe") != "1h") throw std::invalid_argument("instrument_timeframe_mismatch");
        for (const char* key : {"candles", "funding", "open_interest"}) {
            if (!instrument.contains(key)) throw std::invalid_argument(std::string("instrument_series_missing:") + key);
            validate_time_series(instrument.at(key), key, now_ms);
        }
        bool candles_valid = !instrument.at("candles").empty();
        std::int64_t latest_candle_ms = 0;
        for (const auto& candle : instrument.at("candles")) {
            for (const char* key : {"open", "high", "low", "close"}) (void)require_finite_number(candle.at(key), key, true);
            (void)require_finite_number(candle.at("volume"), "volume", false, true);
            (void)require_finite_number(candle.at("volume_base"), "volume_base", false, true);
            (void)require_finite_number(candle.at("volume_quote"), "volume_quote", false, true);
            require_string(candle, "volume_unit");
            require_string(candle, "volume_base_currency");
            require_string(candle, "volume_quote_currency");
            require_string(candle, "retrieved_at_utc");
            if (candle.at("volume_unit") != "contracts" ||
                candle.at("volume_base_currency") != instrument.at("base") ||
                candle.at("volume_quote_currency") != instrument.at("quote"))
                throw std::invalid_argument("ohlcv_volume_unit_or_currency_mismatch");
            if (!candle.contains("closed") || candle.at("closed") != true)
                throw std::invalid_argument("incomplete_candle_in_l1_contract");
            const auto candle_ts = candle.at("timestamp_ms").get<std::int64_t>();
            if (candle_ts + 3'600'000LL > now_ms)
                throw std::invalid_argument("candle_not_completed_at_acquisition");
            const double open = candle.at("open").get<double>();
            const double high = candle.at("high").get<double>();
            const double low = candle.at("low").get<double>();
            const double close = candle.at("close").get<double>();
            if (high < std::max({open, low, close}) || low > std::min({open, high, close}))
                throw std::invalid_argument("ohlcv_relationship_invalid");
            latest_candle_ms = candle.at("timestamp_ms").get<std::int64_t>();
        }
        for (const auto& row : instrument.at("funding")) {
            require_string(row, "retrieved_at_utc");
            if (!row.contains("funding_rate") || !row.contains("mark_price"))
                throw std::invalid_argument("funding_nullable_fields_missing");
            validate_nullable_number(row.at("funding_rate"), "funding_rate");
            validate_nullable_number(row.at("mark_price"), "mark_price", true);
        }
        for (const auto& row : instrument.at("open_interest")) {
            require_string(row, "retrieved_at_utc");
            if (!row.contains("open_interest") || !row.contains("open_interest_base") ||
                !row.contains("open_interest_value_usd"))
                throw std::invalid_argument("open_interest_nullable_fields_missing");
            require_string(row, "open_interest_unit");
            require_string(row, "open_interest_base_currency");
            require_string(row, "open_interest_value_currency");
            if (row.at("open_interest_unit") != "contracts" ||
                row.at("open_interest_base_currency") != instrument.at("base") ||
                row.at("open_interest_value_currency") != "USD")
                throw std::invalid_argument("open_interest_unit_or_currency_mismatch");
            validate_nullable_number(row.at("open_interest"), "open_interest", true);
            validate_nullable_number(row.at("open_interest_base"), "open_interest_base", true);
            validate_nullable_number(row.at("open_interest_value_usd"), "open_interest_value_usd", true);
        }
        const bool latest_fresh = latest_candle_ms > 0 && now_ms >= latest_candle_ms &&
                                  (now_ms - latest_candle_ms) <= 3LL * 3'600'000LL;
        const bool availability_ok = instrument.contains("availability") && instrument.at("availability").is_object();
        if (!availability_ok) throw std::invalid_argument("instrument_availability_missing");
        const auto ohlcv_status = instrument.at("availability").value("ohlcv", std::string{"UNAVAILABLE"});
        const auto funding_status = instrument.at("availability").value("funding", std::string{"UNAVAILABLE"});
        const auto oi_status = instrument.at("availability").value("open_interest", std::string{"UNAVAILABLE"});
        const auto valid_status = [](const std::string& status) {
            return status == "AVAILABLE" || status == "PARTIAL" || status == "UNAVAILABLE";
        };
        if (!valid_status(ohlcv_status) || !valid_status(funding_status) || !valid_status(oi_status))
            throw std::invalid_argument("instrument_availability_status_invalid");
        const bool ohlcv_available = ohlcv_status == "AVAILABLE";
        const bool full_data = funding_status == "AVAILABLE" && oi_status == "AVAILABLE";
        const bool admitted = candles_valid && latest_fresh && ohlcv_available && full_data;
        const std::string reason_code = !candles_valid ? "OHLCV_EMPTY" :
            (!latest_fresh || !ohlcv_available ? "OHLCV_STALE_OR_UNAVAILABLE" :
             (funding_status != "AVAILABLE" ? "FUNDING_DATA_DEGRADED" :
              (oi_status != "AVAILABLE" ? "OPEN_INTEREST_DATA_DEGRADED" : "NO_STRATEGY_ADMITTED")));
        artifact["instruments"].push_back({
            {"instrument_id", instrument.at("instrument_id")}, {"symbol", instrument.at("unified_symbol")},
            {"provider_id", instrument.at("provider_id")},
            {"state", admitted ? "NO_QUALIFIED_SETUP" : "MARKET_DATA_DEGRADED"},
            {"reason_code", reason_code},
            {"data_quality", admitted ? "REAL" : "PARTIAL"},
            {"confidence_status", "NOT_CALIBRATED"}, {"actionable", false},
            {"latest_candle_timestamp_ms", latest_candle_ms}
        });
    }
    return artifact;
}
} // namespace cfss
