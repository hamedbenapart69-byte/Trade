#include <curl/curl.h>

#include "cfss/http_utils.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

bool send_telegram_message(const std::string& token,
                           const std::string& chat_id,
                           const std::string& message) {
    CURL* handle = curl_easy_init();
    if (handle == nullptr) {
        std::cerr << "HTTP client initialization failed\n";
        return false;
    }

    const std::string endpoint =
        "https://api.telegram.org/bot" + token + "/sendMessage";
    const std::string payload = cfss::telegram_payload(chat_id, message);
    std::string response;

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    if (headers == nullptr) {
        curl_easy_cleanup(handle);
        std::cerr << "Could not allocate HTTP headers\n";
        return false;
    }

    curl_easy_setopt(handle, CURLOPT_URL, endpoint.c_str());
    curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(handle, CURLOPT_POST, 1L);
    curl_easy_setopt(handle, CURLOPT_POSTFIELDS, payload.c_str());
    curl_easy_setopt(handle, CURLOPT_POSTFIELDSIZE,
                     static_cast<long>(payload.size()));
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, cfss::append_response);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);

    const CURLcode result = curl_easy_perform(handle);
    long status_code = 0;
    if (result == CURLE_OK) {
        curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &status_code);
    } else {
        std::cerr << "Telegram POST transport failed: "
                  << curl_easy_strerror(result) << '\n';
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(handle);

    std::cout << "Telegram HTTP status: " << status_code << '\n';
    // پاسخ API چاپ می‌شود، اما token هرگز در log قرار نمی‌گیرد.
    std::cout << "Telegram response: " << response << '\n';
    return result == CURLE_OK && status_code >= 200 && status_code < 300 &&
           response.find("\"ok\":true") != std::string::npos;
}

}  // namespace

int main() {
    const char* token_env = std::getenv("TELEGRAM_TOKEN");
    if (token_env == nullptr || token_env[0] == '\0') {
        // سازگاری با نام متغیر استفاده‌شده در scaffold قبلی.
        token_env = std::getenv("TELEGRAM_BOT_TOKEN");
    }
    const char* chat_env = std::getenv("TELEGRAM_CHAT_ID");

    if (token_env == nullptr || chat_env == nullptr ||
        token_env[0] == '\0' || chat_env[0] == '\0') {
        std::cout << "Telegram delivery skipped: secrets are not configured\n";
        std::cout << "Payload fixture: "
                  << cfss::telegram_payload(
                         "CHAT_ID_PLACEHOLDER",
                         "V18.2 C++ Vertical Slice Active")
                  << '\n';
        return EXIT_SUCCESS;
    }

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "libcurl global initialization failed\n";
        return EXIT_FAILURE;
    }

    const bool sent = send_telegram_message(
        token_env, chat_env, "V18.2 C++ Vertical Slice Active");

    curl_global_cleanup();
    return sent ? EXIT_SUCCESS : EXIT_FAILURE;
}
