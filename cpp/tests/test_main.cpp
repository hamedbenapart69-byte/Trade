#include "cfss/http_utils.hpp"
#include "cfss/signal.hpp"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    const std::string input = std::string{"quote: \""} + '\n' + '\t';
    if (cfss::json_escape(input) != "quote: \\\"\\n\\t") {
        std::cerr << "JSON escaping test failed\n"; return EXIT_FAILURE;
    }

    const auto levels = cfss::calculate_long_levels(65000.0, 64000.0);
    if (levels.entry_price != 65000.0 || levels.stop_loss != 64000.0 ||
        levels.take_profit != 67000.0 || std::abs(levels.risk_reward - 2.0) > 1e-12 ||
        levels.used_fallback) {
        std::cerr << "Five-candle low LONG level calculation failed\n"; return EXIT_FAILURE;
    }

    const auto fallback = cfss::calculate_long_levels(65000.0, 0.0);
    if (std::abs(fallback.stop_loss - 64350.0) > 1e-9 ||
        std::abs(fallback.take_profit - 66300.0) > 1e-9 ||
        std::abs(fallback.risk_reward - 2.0) > 1e-12 || !fallback.used_fallback) {
        std::cerr << "Invalid stop 1% fallback calculation failed\n"; return EXIT_FAILURE;
    }

    const cfss::ActionableSignal sample{
        "SIG-BTC-LONG-123", "BTC-USDT-SWAP", "BUY_NOW", "LONG",
        65000.0, 64000.0, 67000.0, 2.0, "LRT_SMA20_PROXY",
        "OKX", "2026-11-17T14:00:00Z", "PROXY", "15m",
        "Close above SMA20", "Close at or below SMA20", false
    };
    const std::string json = cfss::format_signal_json(sample);
    const std::string markdown = cfss::format_signal_markdown(sample);
    if (json.find("\"signal_id\":\"SIG-BTC-LONG-123\"") == std::string::npos ||
        json.find("\"state\":\"BUY_NOW\"") == std::string::npos ||
        json.find("\"direction\":\"LONG\"") == std::string::npos ||
        json.find("\"entry_price\":65000") == std::string::npos ||
        json.find("\"stop_loss\":64000") == std::string::npos ||
        json.find("\"take_profit\":67000") == std::string::npos ||
        json.find("\"risk_reward\":2") == std::string::npos ||
        json.find("\"strategy\":\"LRT_SMA20_PROXY\"") == std::string::npos ||
        json.find("\"provider\":\"OKX\"") == std::string::npos ||
        json.find("\"data_quality\":\"PROXY\"") == std::string::npos ||
        json.find("\"confidence_status\":\"NOT_CALIBRATED\"") == std::string::npos) {
        std::cerr << "Actionable signal JSON schema test failed: " << json << '\n';
        return EXIT_FAILURE;
    }
    if (markdown.find("Entry: `65000.00`") == std::string::npos ||
        markdown.find("Stop Loss: `64000.00`") == std::string::npos ||
        markdown.find("Take Profit: `67000.00`") == std::string::npos ||
        markdown.find("Risk/Reward: *1:2.00*") == std::string::npos) {
        std::cerr << "Telegram Markdown formatting test failed: " << markdown << '\n';
        return EXIT_FAILURE;
    }

    const auto okx = cfss::extract_json_number(R"({"code":"0","data":[{"last":"64941.25"}]})", "last");
    const auto bybit = cfss::extract_json_number(R"({"retCode":0,"result":{"list":[{"lastPrice":"65000"}]}})", "lastPrice");
    const auto invalid = cfss::extract_json_number(R"({"price":"not-a-price"})", "price");
    if (!okx || *okx != "64941.25" || !bybit || *bybit != "65000" || invalid) {
        std::cerr << "Provider JSON validation test failed\n"; return EXIT_FAILURE;
    }
    std::cout << "Actionable signal levels, JSON schema, Markdown and provider tests passed\n";
    return EXIT_SUCCESS;
}
