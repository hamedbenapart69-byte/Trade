#pragma once

#include <string>
#include <string_view>

namespace cfss::provider_policy {

// فقط دامنه‌های ارائه‌دهندگان مستقل داده مجازند؛ دامنه‌های صرافی عمداً allowlist نیستند.
inline bool is_allowed_independent_provider_url(std::string_view url) {
    constexpr std::string_view scheme = "https://";
    if (url.substr(0, scheme.size()) != scheme) return false;

    const auto authority_start = scheme.size();
    const auto authority_end = url.find_first_of("/?#", authority_start);
    const auto authority = url.substr(authority_start,
        authority_end == std::string_view::npos
            ? url.size() - authority_start
            : authority_end - authority_start);

    // Reject user-info, escaped hosts, backslashes, whitespace, and non-HTTPS ports.
    if (authority.empty() ||
        authority.find('@') != std::string_view::npos ||
        authority.find('\\') != std::string_view::npos ||
        authority.find('%') != std::string_view::npos ||
        authority.find(' ') != std::string_view::npos ||
        authority.find('\t') != std::string_view::npos ||
        authority.find('\r') != std::string_view::npos ||
        authority.find('\n') != std::string_view::npos) {
        return false;
    }

    const auto port_separator = authority.find(':');
    const auto host = authority.substr(0U, port_separator);
    if (port_separator != std::string_view::npos &&
        authority.substr(port_separator + 1U) != "443") {
        return false;
    }

    constexpr std::string_view allowed_hosts[] = {
        "api.coinpaprika.com",
        "api.coingecko.com",
        "pro-api.coinmarketcap.com",
        "api.alternative.me",
        "api.coinalyze.net",
        "api.coinstats.app",
        "api.coinstats.com",
        "openapiv1.coinstats.app"
    };
    for (const auto allowed : allowed_hosts) {
        if (host == allowed) return true;
    }
    return false;
}

} // namespace cfss::provider_policy
