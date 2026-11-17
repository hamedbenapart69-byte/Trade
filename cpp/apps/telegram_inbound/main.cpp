#include "cfss/telegram_l3.hpp"
#include <cstdlib>
#include <iostream>

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: telegram_inbound <inbound-state.json> <run-manifest.json>\n";
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
        const auto previous_state = cfss::telegram::load_json_or_default(argv[1], cfss::telegram::default_inbound_state());
        const long long previous_update_id = previous_state.value("last_update_id", 0LL);
        const int result = cfss::telegram::run_inbound(argv[1], token, chat_id);
        cfss::telegram::record_inbound_manifest(argv[2], argv[1], previous_update_id, result);
        curl_global_cleanup();
        return result;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "TELEGRAM_INBOUND_FAILED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
