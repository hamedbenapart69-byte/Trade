#include "cfss/okx_provider.hpp"

#include <cstdlib>
#include <iostream>
#include <set>
#include <string>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    const std::set<std::string> verified{"BTC", "ETH", "SOL", "DOGE"};
    require(cfss::okx::is_verified_crypto_underlying("BTC", verified),
            "verified crypto base symbol is admitted");
    require(cfss::okx::is_verified_crypto_underlying("eth", verified),
            "crypto symbols are case-normalized");
    require(!cfss::okx::is_verified_crypto_underlying("SOXL", {"BTC", "SOXL"}),
            "known leveraged equity ETF is excluded even if symbol collides");
    require(!cfss::okx::is_verified_crypto_underlying("NVDA", {"BTC", "NVDA"}),
            "known equity underlying is excluded");
    require(!cfss::okx::is_verified_crypto_underlying("XAU", {"BTC", "XAU"}),
            "commodity underlying is excluded");
    require(!cfss::okx::is_verified_crypto_underlying("SNDK", verified),
            "unverified symbol is excluded from the crypto universe");
    std::cout << "CRYPTO_UNIVERSE_TESTS_PASS\n";
    return 0;
}
