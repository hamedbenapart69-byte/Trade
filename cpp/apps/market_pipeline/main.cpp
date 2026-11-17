#include <curl/curl.h>

#include "cfss/http_utils.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

namespace {

struct HttpResult {
    CURLcode transport{CURLE_FAILED_INIT};
    long status_code{0};
    std::string response;
};

HttpResult perform_get(std::string_view url) {
    HttpResult result;
    CURL* handle = curl_easy_init();
    if (handle == nullptr) {
        std::cerr << "HTTP client initialization failed\n";
        return result;
    }

    const std::string url_string{url};
    curl_easy_setopt(handle, CURLOPT_URL, url_string.c_str());
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, cfss::append_response);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, &result.response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(handle, CURLOPT_USERAGENT, "CFSS-CPP/0.3");
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);

    result.transport = curl_easy_perform(handle);
    if (result.transport == CURLE_OK) {
        curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &result.status_code);
    } else {
        std::cerr << "HTTP GET transport failed: "
                  << curl_easy_strerror(result.transport) << '\n';
    }

    curl_easy_cleanup(handle);
    return result;
}

bool is_http_success(const HttpResult& result) {
    return result.transport == CURLE_OK &&
           result.status_code >= 200 && result.status_code < 300;
}

void print_result(std::string_view provider, const HttpResult& result) {
    std::cout << provider << " HTTP status: " << result.status_code << '\n';
    std::cout << provider << " response: " << result.response << '\n';
}

}  // namespace

int main() {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "libcurl global initialization failed\n";
        return EXIT_FAILURE;
    }

    // Binance حفظ می‌شود؛ در صورت محدودیت منطقه‌ای/خطای منبع، OKX جایگزین است.
    constexpr std::string_view binance_endpoint =
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT";
    constexpr std::string_view okx_endpoint =
        "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP";

    const HttpResult binance = perform_get(binance_endpoint);
    print_result("Binance", binance);

    bool data_available = is_http_success(binance);
    if (!data_available) {
        std::cout << "Binance unavailable; activating OKX public-data fallback\n";
        const HttpResult okx = perform_get(okx_endpoint);
        print_result("OKX", okx);
        data_available = is_http_success(okx);
    }

    curl_global_cleanup();

    if (!data_available) {
        std::cerr << "All configured public market-data endpoints unavailable\n";
        return EXIT_FAILURE;
    }

    std::cout << "Public market-data HTTP check passed\n";
    return EXIT_SUCCESS;
}
