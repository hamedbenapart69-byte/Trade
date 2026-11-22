#include "cfss/bitget_provider_probe.hpp"

#include <curl/curl.h>

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    std::vector<std::string> symbols;
    if (argc < 2) {
        symbols = {"BTCUSDT", "ETHUSDT"};
    } else {
        for (int index = 1; index < argc; ++index) {
            if (!argv[index]) {
                std::cerr << "invalid_null_symbol_argument\n";
                return EXIT_FAILURE;
            }
            symbols.emplace_back(argv[index]);
        }
    }
    for (const auto& symbol : symbols) {
        if (!cfss::bitget::valid_symbol(symbol)) {
            std::cerr << "invalid_symbol=" << symbol << '\n';
            return EXIT_FAILURE;
        }
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "curl_global_init_failed\n";
        return EXIT_FAILURE;
    }
    int exit_code = EXIT_FAILURE;
    try {
        const auto report = cfss::bitget::probe(symbols);
        std::cout << report.dump(2) << '\n';
        exit_code = report.value("status", std::string{"UNAVAILABLE"}) == "PASS"
            ? EXIT_SUCCESS : EXIT_FAILURE;
    } catch (const std::exception& error) {
        std::cerr << "BITGET_PROBE_FATAL=" << error.what() << '\n';
        exit_code = EXIT_FAILURE;
    }
    curl_global_cleanup();
    return exit_code;
}
