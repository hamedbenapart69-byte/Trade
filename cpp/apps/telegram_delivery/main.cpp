#include <curl/curl.h>
#include "cfss/signal.hpp"
#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    const char* signal_message = std::getenv("CFSS_SIGNAL_MESSAGE");
    if (!token || !chat_id || !signal_message || token[0] == '\0' ||
        chat_id[0] == '\0' || signal_message[0] == '\0') {
        std::cerr << "Required environment variables: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, CFSS_SIGNAL_MESSAGE\n";
        return EXIT_FAILURE;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return EXIT_FAILURE;
    const bool sent = cfss::send_telegram_message(token, chat_id, signal_message);
    curl_global_cleanup();
    return sent ? EXIT_SUCCESS : EXIT_FAILURE;
}
