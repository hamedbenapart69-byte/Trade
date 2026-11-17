#include <curl/curl.h>

#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

namespace {

size_t discard_response(char* data, size_t size, size_t count, void*) {
    return size * count;
}

bool perform_get(std::string_view url) {
    CURL* handle = curl_easy_init();
    if (handle == nullptr) {
        std::cerr << "HTTP client initialization failed\n";
        return false;
    }

    const std::string url_string{url};
    curl_easy_setopt(handle, CURLOPT_URL, url_string.c_str());
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, discard_response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(handle, CURLOPT_USERAGENT, "CFSS-CPP/0.1");

    const CURLcode result = curl_easy_perform(handle);
    long status_code = 0;
    if (result == CURLE_OK) {
        curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &status_code);
    } else {
        std::cerr << "HTTP request failed: " << curl_easy_strerror(result) << '\n';
    }

    curl_easy_cleanup(handle);
    return result == CURLE_OK && status_code >= 200 && status_code < 300;
}

}  // namespace

int main() {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "libcurl global initialization failed\n";
        return EXIT_FAILURE;
    }

    // اتصال عمومی و فقط خواندنی؛ هیچ مسیر حساب معاملاتی یا سفارش وجود ندارد.
    constexpr std::string_view endpoint =
        "https://www.okx.com/api/v5/public/instruments?instType=SWAP";

    const bool request_ok = perform_get(endpoint);
    curl_global_cleanup();

    if (!request_ok) {
        std::cerr << "Market data connectivity check did not pass\n";
        return EXIT_FAILURE;
    }

    std::cout << "Market pipeline HTTP connectivity check passed\n";
    return EXIT_SUCCESS;
}
