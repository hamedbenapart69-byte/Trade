#include <curl/curl.h>

#include <cstdlib>
#include <iostream>
#include <string>

namespace {

size_t discard_response(char* data, size_t size, size_t count, void*) {
    return size * count;
}

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
    char* escaped_chat_id = curl_easy_escape(handle, chat_id.c_str(), 0);
    char* escaped_message = curl_easy_escape(handle, message.c_str(), 0);

    if (escaped_chat_id == nullptr || escaped_message == nullptr) {
        if (escaped_chat_id != nullptr) curl_free(escaped_chat_id);
        if (escaped_message != nullptr) curl_free(escaped_message);
        curl_easy_cleanup(handle);
        return false;
    }

    const std::string payload =
        "chat_id=" + std::string{escaped_chat_id} +
        "&text=" + std::string{escaped_message};

    curl_free(escaped_chat_id);
    curl_free(escaped_message);

    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(
        headers, "Content-Type: application/x-www-form-urlencoded");

    curl_easy_setopt(handle, CURLOPT_URL, endpoint.c_str());
    curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(handle, CURLOPT_POST, 1L);
    curl_easy_setopt(handle, CURLOPT_POSTFIELDS, payload.c_str());
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, discard_response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);

    const CURLcode result = curl_easy_perform(handle);
    long status_code = 0;
    if (result == CURLE_OK) {
        curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &status_code);
    } else {
        std::cerr << "Telegram HTTP request failed: "
                  << curl_easy_strerror(result) << '\n';
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(handle);
    return result == CURLE_OK && status_code >= 200 && status_code < 300;
}

}  // namespace

int main() {
    const char* token_env = std::getenv("TELEGRAM_BOT_TOKEN");
    const char* chat_env = std::getenv("TELEGRAM_CHAT_ID");

    // نبود Secret به‌صورت امن و بدون چاپ مقدار آن مدیریت می‌شود.
    if (token_env == nullptr || chat_env == nullptr ||
        token_env[0] == '\0' || chat_env[0] == '\0') {
        std::cout << "Telegram delivery skipped: credentials are not configured\n";
        return EXIT_SUCCESS;
    }

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "libcurl global initialization failed\n";
        return EXIT_FAILURE;
    }

    const bool sent = send_telegram_message(
        token_env, chat_env, "CFSS C++ Telegram connectivity test");

    curl_global_cleanup();
    return sent ? EXIT_SUCCESS : EXIT_FAILURE;
}
