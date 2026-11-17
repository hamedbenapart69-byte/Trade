#include "cfss/http_utils.hpp"
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
    if (payload != expected) { std::cerr << "Telegram payload test failed: " << payload << '\n'; return EXIT_FAILURE; }
    const auto okx = cfss::extract_json_number(R"({"code":"0","data":[{"last":"64941.25"}]})", "last");
    const auto bybit = cfss::extract_json_number(R"({"retCode":0,"result":{"list":[{"lastPrice":"65000"}]}})", "lastPrice");
    const auto invalid = cfss::extract_json_number(R"({"price":"not-a-price"})", "price");
    if (!okx || *okx != "64941.25" || !bybit || *bybit != "65000" || invalid) {
        std::cerr << "Provider JSON price validation test failed\n"; return EXIT_FAILURE;
    }
    std::cout << "Telegram payload and provider price validation tests passed\n";
    return EXIT_SUCCESS;
}