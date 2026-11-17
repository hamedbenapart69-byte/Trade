#include "cfss/http_utils.hpp"
#include "cfss/signal.hpp"
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    const std::string input = std::string{"quote: \""} + '\n' + '\t';
    if (cfss::json_escape(input) != "quote: \\\"\\n\\t") {
        std::cerr << "JSON escaping test failed\n"; return EXIT_FAILURE;
    }
    const std::string payload = cfss::telegram_payload("12345", "V18.2 C++ Vertical Slice Active");
    const std::string expected = R"({"chat_id":"12345","text":"V18.2 C++ Vertical Slice Active"})";
    if (payload != expected) { std::cerr << "Telegram payload test failed\n"; return EXIT_FAILURE; }

    const cfss::SignalSnapshot sample{
        "SIG-BTC-123", "BTC-USDT-SWAP", "BULLISH", 65000.25,
        "SMA_20", 64900.5, "OKX", "2026-11-17T14:00:00Z"
    };
    const std::string json = cfss::format_signal_json(sample);
    if (json.find("\"current_price\":65000.25") == std::string::npos ||
        json.find("\"indicator_value\":64900.5") == std::string::npos ||
        json.find("\"data_provider\":\"OKX\"") == std::string::npos ||
        json.find("\"direction_bias\":\"BULLISH\"") == std::string::npos) {
        std::cerr << "Signal schema formatting test failed: " << json << '\n';
        return EXIT_FAILURE;
    }
    const auto okx = cfss::extract_json_number(R"({"code":"0","data":[{"last":"64941.25"}]})", "last");
    const auto bybit = cfss::extract_json_number(R"({"retCode":0,"result":{"list":[{"lastPrice":"65000"}]}})", "lastPrice");
    const auto invalid = cfss::extract_json_number(R"({"price":"not-a-price"})", "price");
    if (!okx || *okx != "64941.25" || !bybit || *bybit != "65000" || invalid) {
        std::cerr << "Provider JSON validation test failed\n"; return EXIT_FAILURE;
    }
    std::cout << "Signal JSON, Telegram payload and provider validation tests passed\n";
    return EXIT_SUCCESS;
}