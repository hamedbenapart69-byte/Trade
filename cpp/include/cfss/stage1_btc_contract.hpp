#pragma once

#include "cfss/hash.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <stdexcept>
#include <string>

namespace cfss::stage1 {

inline void require_text(const nlohmann::json& value, const char* key) {
    if (!value.is_object() || !value.contains(key) || !value.at(key).is_string() ||
        value.at(key).get<std::string>().empty()) {
        throw std::invalid_argument(std::string("stage1_required_text_invalid:") + key);
    }
}

inline double finite_number(const nlohmann::json& value, const char* key,
                            bool positive = false, bool non_negative = false) {
    if (!value.is_number()) {
        throw std::invalid_argument(std::string("stage1_number_invalid:") + key);
    }
    const double number = value.get<double>();
    if (!std::isfinite(number) || (positive && number <= 0.0) ||
        (non_negative && number < 0.0)) {
        throw std::invalid_argument(std::string("stage1_number_out_of_range:") + key);
    }
    return number;
}

inline void validate_btc_l1(const nlohmann::json& contract,
                            const std::string& archive_bytes,
                            std::int64_t now_ms) {
    if (!contract.is_object() ||
        contract.value("schema_version", std::string{}) != "1.0.0" ||
        contract.value("artifact_type", std::string{}) != "cfss_stage1_btc_l1_v1") {
        throw std::invalid_argument("stage1_schema_or_artifact_type_invalid");
    }
    require_text(contract, "run_id");
    require_text(contract, "scan_id");
    require_text(contract, "acquired_at_utc");

    if (contract.value("signal_generation_enabled", true) != false ||
        contract.value("trading_decision", std::string{}) != "NOT_IN_SCOPE") {
        throw std::invalid_argument("stage1_trading_must_remain_disabled");
    }

    if (!contract.contains("provider") || !contract.at("provider").is_object() ||
        contract.at("provider").value("primary_provider_id", std::string{}) != "binance_vision" ||
        contract.at("provider").value("data_class", std::string{}) != "DAILY_ARCHIVE_DELAYED" ||
        contract.at("provider").value("realtime", true) != false ||
        contract.at("provider").value("fallback_used", true) != false) {
        throw std::invalid_argument("stage1_provider_identity_invalid");
    }

    if (!contract.contains("window") || !contract.at("window").is_object() ||
        contract.at("window").value("timeframe", std::string{}) != "1h" ||
        !contract.at("window").contains("start_ms") ||
        !contract.at("window").contains("end_ms") ||
        !contract.at("window").at("start_ms").is_number_integer() ||
        !contract.at("window").at("end_ms").is_number_integer()) {
        throw std::invalid_argument("stage1_window_invalid");
    }

    if (!contract.contains("provenance") || !contract.at("provenance").is_object() ||
        contract.at("provenance").value("sha256_verified", false) != true ||
        !contract.at("provenance").contains("source_files") ||
        !contract.at("provenance").at("source_files").is_array() ||
        contract.at("provenance").at("source_files").size() != 1U) {
        throw std::invalid_argument("stage1_provenance_invalid");
    }

    const auto& source = contract.at("provenance").at("source_files").at(0);
    require_text(source, "filename");
    require_text(source, "archive_url");
    require_text(source, "checksum_url");
    require_text(source, "sha256");
    require_text(source, "checksum_file_sha256");
    const std::string expected_sha = source.at("sha256").get<std::string>();
    if (expected_sha.size() != 64U || expected_sha != cfss::sha256_hex(archive_bytes)) {
        throw std::invalid_argument("stage1_archive_sha256_mismatch");
    }
    const std::string checksum_sha = source.at("checksum_file_sha256").get<std::string>();
    if (checksum_sha.size() != 64U ||
        !std::all_of(checksum_sha.begin(), checksum_sha.end(), [](unsigned char ch) {
            return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
        })) {
        throw std::invalid_argument("stage1_checksum_file_sha256_invalid");
    }

    if (!contract.contains("instruments") || !contract.at("instruments").is_array() ||
        contract.at("instruments").size() != 1U) {
        throw std::invalid_argument("stage1_exactly_one_instrument_required");
    }

    const auto& instrument = contract.at("instruments").at(0);
    for (const char* key : {"instrument_id", "unified_symbol", "base", "quote", "settle",
                            "contract_type", "provider_id", "timeframe"}) {
        require_text(instrument, key);
    }
    if (instrument.at("instrument_id") != "BTCUSDT" ||
        instrument.at("unified_symbol") != "BTC/USDT:USDT" ||
        instrument.at("base") != "BTC" || instrument.at("quote") != "USDT" ||
        instrument.at("settle") != "USDT" ||
        instrument.at("contract_type") != "linear_perpetual" ||
        instrument.at("provider_id") != "binance_vision" ||
        instrument.at("timeframe") != "1h") {
        throw std::invalid_argument("stage1_instrument_identity_invalid");
    }

    if (!instrument.contains("candles") || !instrument.at("candles").is_array() ||
        instrument.at("candles").size() != 24U ||
        !instrument.contains("funding") || !instrument.at("funding").is_array() ||
        !instrument.at("funding").empty() ||
        !instrument.contains("open_interest") || !instrument.at("open_interest").is_array() ||
        !instrument.at("open_interest").empty()) {
        throw std::invalid_argument("stage1_series_coverage_invalid");
    }

    if (!instrument.contains("availability") || !instrument.at("availability").is_object() ||
        instrument.at("availability").value("ohlcv", std::string{}) != "AVAILABLE" ||
        instrument.at("availability").value("funding", std::string{}) != "UNAVAILABLE" ||
        instrument.at("availability").value("open_interest", std::string{}) != "UNAVAILABLE") {
        throw std::invalid_argument("stage1_availability_status_invalid");
    }

    std::int64_t previous_ts = 0;
    std::int64_t latest_close_ms = 0;
    for (const auto& candle : instrument.at("candles")) {
        if (!candle.is_object() || !candle.contains("timestamp_ms") ||
            !candle.at("timestamp_ms").is_number_integer() ||
            !candle.contains("close_time_ms") || !candle.at("close_time_ms").is_number_integer()) {
            throw std::invalid_argument("stage1_candle_timestamp_invalid");
        }
        const auto ts = candle.at("timestamp_ms").get<std::int64_t>();
        const auto close_ms = candle.at("close_time_ms").get<std::int64_t>();
        if (ts <= previous_ts || ts <= 0 || ts % 3'600'000LL != 0 ||
            (previous_ts != 0 && ts - previous_ts != 3'600'000LL)) {
            throw std::invalid_argument("stage1_candle_order_or_gap_invalid");
        }
        if (close_ms < ts || close_ms >= ts + 3'600'000LL || close_ms >= now_ms) {
            throw std::invalid_argument("stage1_candle_not_closed");
        }
        const double open = finite_number(candle.at("open"), "open", true);
        const double high = finite_number(candle.at("high"), "high", true);
        const double low = finite_number(candle.at("low"), "low", true);
        const double close = finite_number(candle.at("close"), "close", true);
        (void)finite_number(candle.at("volume"), "volume", false, true);
        (void)finite_number(candle.at("volume_quote"), "volume_quote", false, true);
        (void)finite_number(candle.at("taker_buy_base"), "taker_buy_base", false, true);
        (void)finite_number(candle.at("taker_buy_quote"), "taker_buy_quote", false, true);
        if (high < std::max({open, low, close}) || low > std::min({open, high, close})) {
            throw std::invalid_argument("stage1_ohlc_relationship_invalid");
        }
        if (candle.value("price_currency", std::string{}) != "USDT" ||
            candle.value("volume_unit", std::string{}) != "base_asset" ||
            candle.value("volume_base_currency", std::string{}) != "BTC" ||
            candle.value("volume_quote_currency", std::string{}) != "USDT" ||
            candle.value("closed", false) != true) {
            throw std::invalid_argument("stage1_volume_unit_or_closed_flag_invalid");
        }
        require_text(candle, "retrieved_at_utc");
        previous_ts = ts;
        latest_close_ms = close_ms;
    }

    const auto& window = contract.at("window");
    const auto& candles = instrument.at("candles");
    const auto first_ts = candles.front().at("timestamp_ms").get<std::int64_t>();
    if (window.at("start_ms").get<std::int64_t>() != first_ts ||
        window.at("end_ms").get<std::int64_t>() != latest_close_ms ||
        window.at("closed_candles").get<std::int64_t>() != 24) {
        throw std::invalid_argument("stage1_window_does_not_match_candles");
    }
    if (source.at("bytes").get<std::size_t>() != archive_bytes.size() ||
        source.at("row_count").get<std::size_t>() != 24U ||
        source.at("first_timestamp_ms").get<std::int64_t>() != first_ts ||
        source.at("last_timestamp_ms").get<std::int64_t>() != candles.back().at("timestamp_ms").get<std::int64_t>()) {
        throw std::invalid_argument("stage1_archive_provenance_does_not_match_payload");
    }

    const auto& freshness = contract.at("freshness");
    if (!freshness.is_object() ||
        freshness.value("status", std::string{}) != "DAILY_ARCHIVE_DELAYED" ||
        freshness.value("maximum_staleness_ms", std::int64_t{0}) != 26LL * 3'600'000LL ||
        freshness.value("latest_candle_close_ms", std::int64_t{0}) != latest_close_ms) {
        throw std::invalid_argument("stage1_freshness_metadata_invalid");
    }
    const auto staleness_ms = now_ms - latest_close_ms;
    const auto recorded_staleness_ms = freshness.value("staleness_ms", std::int64_t{-1});
    const auto staleness_drift_ms = std::llabs(recorded_staleness_ms - staleness_ms);
    // اختلاف چند ثانیه بین زمان دریافت Python و اعتبارسنجی C++ طبیعی است.
    if (staleness_ms < 0 || staleness_ms >= 26LL * 3'600'000LL ||
        recorded_staleness_ms < 0 || recorded_staleness_ms >= 26LL * 3'600'000LL ||
        staleness_drift_ms > 5LL * 60'000LL) {
        throw std::invalid_argument("stage1_candle_stale_or_freshness_clock_drift");
    }
}

inline nlohmann::json build_no_signal_l2(const nlohmann::json& contract,
                                         std::int64_t now_ms) {
    const auto& instrument = contract.at("instruments").at(0);
    nlohmann::json artifact = {
        {"artifact_type", "cfss_l2_status_v1"},
        {"source_schema_version", "1.0.0"},
        {"source_run_id", contract.at("run_id")},
        {"source_scan_id", contract.at("scan_id")},
        {"created_at_epoch_ms", now_ms},
        {"stage", "STAGE_1_DATA_VALIDATION_ONLY"},
        {"signal_generation_enabled", false},
        {"instruments", nlohmann::json::array({
            {
                {"instrument_id", "BTCUSDT"},
                {"symbol", "BTCUSDT"},
                {"provider_id", "binance_vision"},
                {"state", "NO_QUALIFIED_SETUP"},
                {"reason_code", "STAGE1_DATA_VALIDATION_ONLY_NO_STRATEGY"},
                {"data_quality", "REAL"},
                {"confidence_status", "NOT_CALIBRATED"},
                {"actionable", false},
                {"latest_candle_timestamp_ms", instrument.at("candles").back().at("timestamp_ms")}
            }
        })}
    };
    cfss::add_artifact_hash(artifact);
    return artifact;
}

} // namespace cfss::stage1
