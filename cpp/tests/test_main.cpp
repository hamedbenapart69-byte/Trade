#include "cfss/http_utils.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    const std::string input =
        std::string{"quote: \""} + '\n' + '\t';
    const std::string escaped = cfss::json_escape(input);
    if (escaped != "quote: \\\"\\n\\t") {
        std::cerr << "JSON escaping test failed: " << escaped << '\n';
        return EXIT_FAILURE;
    }

    const std::string payload = cfss::telegram_payload(
        "12345", "V18.2 C++ Vertical Slice Active");
    const std::string expected =
        R"({"chat_id":"12345","text":"V18.2 C++ Vertical Slice Active"})";
    if (payload != expected) {
        std::cerr << "Telegram payload test failed: " << payload << '\n';
        return EXIT_FAILURE;
    }

    std::cout << "Telegram payload fixture: " << payload << '\n';
    std::cout << "All C++ unit checks passed\n";
    return EXIT_SUCCESS;
}
