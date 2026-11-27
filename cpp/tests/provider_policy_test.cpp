#include "cfss/provider_policy.hpp"

#include <iostream>
#include <string_view>

int main() {
    struct TestCase { std::string_view url; bool expected; };
    constexpr TestCase cases[] = {
        {"https://api.coinpaprika.com/v1/coins", true},
        {"https://api.coingecko.com/api/v3/ping", true},
        {"https://pro-api.coinmarketcap.com/v1/cryptocurrency/map", true},
        {"https://api.alternative.me/fng/", true},
        {"https://api.coinalyze.net/v1/funding-rate", true},
        {"https://api.coinstats.app/public/v1/coins", true},
        {"https://www.okx.com/api/v5/market/tickers", false},
        {"https://api.bybit.com/v5/market/time", false},
        {"https://fapi.binance.com/fapi/v1/ping", false},
        {"https://api-futures.kucoin.com/api/v1/contracts/active", false},
        {"https://api.bitget.com/api/v2/mix/market/ticker", false},
        {"https://contract.mexc.com/api/v1/contract/detail", false},
        {"https://api.coingecko.com.evil.example/api/v3/ping", false},
        {"https://openapiv1.coinstats.app/v1/coins", true},
        {"https://api.coingecko.com:443/api/v3/ping", true},
        {"https://api.coingecko.com:8443/api/v3/ping", false},
        {"https://api.coingecko.com:443@evil.example/api/v3/ping", false},
        {"http://api.coingecko.com/api/v3/ping", false}
    };
    for (const auto& test : cases) {
        const bool actual = cfss::provider_policy::is_allowed_independent_provider_url(test.url);
        if (actual != test.expected) {
            std::cerr << "provider_policy mismatch: " << test.url << '\n';
            return 1;
        }
    }
    std::cout << "PROVIDER_POLICY_TEST=PASS cases=" << (sizeof(cases) / sizeof(cases[0])) << '\n';
    return 0;
}
