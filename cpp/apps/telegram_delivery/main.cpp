#include <curl/curl.h>
#include "cfss/signal.hpp"
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    const char* signal_json = std::getenv("CFSS_SIGNAL_JSON");
    if (!token || !chat_id || !signal_json || token[0] == '\0' ||
        chat_id[0] == '\0' || signal_json[0] == '\0') {
        std::cerr << "Required environment variables: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, CFSS_SIGNAL_JSON\n";
        return EXIT_FAILURE;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return EXIT_FAILURE;
    const bool sent = cfss::send_telegram_json(token, chat_id, signal_json);
    curl_global_cleanup();
    return sent ? EXIT_SUCCESS : EXIT_FAILURE;
}