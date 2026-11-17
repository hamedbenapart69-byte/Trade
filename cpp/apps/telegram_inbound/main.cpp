#include "cfss/telegram_l3.hpp"
#include <cstdlib>
#include <iostream>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: telegram_inbound <inbound-state.json>\n";
        return EXIT_FAILURE;
    }
    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    if (!token || !chat_id || token[0] == '\0' || chat_id[0] == '\0') {
        std::cerr << "TELEGRAM_CONFIGURATION_MISSING\n";
        return EXIT_FAILURE;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return EXIT_FAILURE;
    try {
        const int result = cfss::telegram::run_inbound(argv[1], token, chat_id);
        curl_global_cleanup();
        return result;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "TELEGRAM_INBOUND_FAILED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
