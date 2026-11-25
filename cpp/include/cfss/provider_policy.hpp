#pragma once

#include <string>
#include <string_view>

namespace cfss::provider_policy {

// فقط دامنه‌های ارائه‌دهندگان مستقل داده مجازند؛ دامنه‌های صرافی عمداً allowlist نیستند.
inline bool is_allowed_independent_provider_url(std::string_view url) {
    constexpr std::string_view scheme = "https://";
    if (url.substr(0, scheme.size()) != scheme) return false;

    const auto host_start = scheme.size();
    const auto host_end = url.find_first_of("/:?#", host_start);
    const auto host = url.substr(host_start,
        host_end == std::string_view::npos ? url.size() - host_start : host_end - host_start);

    constexpr std::string_view allowed_hosts[] = {
        "api.coinpaprika.com",
        "api.coingecko.com",
        "pro-api.coinmarketcap.com",
        "api.alternative.me",
        "api.coinalyze.net",
        "api.coinstats.app",
        "api.coinstats.com"
    };
    for (const auto allowed : allowed_hosts) {
        if (host == allowed) return true;
    }
    return false;
}

} // namespace cfss::provider_policy
