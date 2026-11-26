// Non-production KuCoin public-market-data diagnostic. Public GET requests only: no credentials,
// no Telegram, no persistence. Prints the live_probe JSON for each requested base symbol.
#include "cfss/kucoin_provider.hpp"
#include <cstdlib>
#include <iostream>

int main(int argc, char** argv) {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return EXIT_FAILURE;
    int failures = 0;
    for (int i = 1; i < argc; ++i) {
        try {
            const auto probe = cfss::kucoin::live_probe(argv[i]);
            std::cout << "KUCOIN_DIAG base=" << argv[i] << ' ' << probe.dump() << '\n';
            if (probe.value("status", std::string{"FAIL"}) != "PASS") ++failures;
        } catch (const std::exception& error) {
            std::cout << "KUCOIN_DIAG base=" << argv[i] << " status=ERROR error=" << error.what() << '\n';
            ++failures;
        }
    }
    curl_global_cleanup();
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
