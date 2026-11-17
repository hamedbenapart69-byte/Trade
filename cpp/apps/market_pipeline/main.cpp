#include <curl/curl.h>

#include "cfss/http_utils.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

namespace {

bool perform_get(std::string_view url) {
    CURL* handle = curl_easy_init();
    if (handle == nullptr) {
        std::cerr << "HTTP client initialization failed\n";
        return false;
    }

    const std::string url_string{url};
    std::string response;
    curl_easy_setopt(handle, CURLOPT_URL, url_string.c_str());
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, cfss::append_response);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(handle, CURLOPT_USERAGENT, "CFSS-CPP/0.2");
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);

    const CURLcode result = curl_easy_perform(handle);
    long status_code = 0;
    if (result == CURLE_OK) {
        curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &status_code);
    } else {
        std::cerr << "HTTP GET failed: " << curl_easy_strerror(result) << '\n';
    }

    curl_easy_cleanup(handle);
    std::cout << "Binance HTTP status: " << status_code << '\n';
    std::cout << "Binance response: " << response << '\n';
    return result == CURLE_OK && status_code >= 200 && status_code < 300;
}

}  // namespace

int main() {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "libcurl global initialization failed\n";
        return EXIT_FAILURE;
    }

    // فقط endpoint عمومی قیمت؛ بدون حساب کاربری یا امکان ثبت سفارش.
    constexpr std::string_view endpoint =
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT";

    const bool request_ok = perform_get(endpoint);
    curl_global_cleanup();

    if (!request_ok) {
        std::cerr << "Binance public market-data GET did not pass\n";
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
