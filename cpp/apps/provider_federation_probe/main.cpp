#include "cfss/provider_federation.hpp"

#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>

namespace {
using json = nlohmann::json;

void write_output(const std::string& path, const json& output) {
    if (path.empty() || path == "-") {
        std::cout << output.dump(2) << '\n';
        return;
    }
    const std::filesystem::path target{path};
    if (!target.parent_path().empty()) std::filesystem::create_directories(target.parent_path());
    const auto temporary = target.string() + ".tmp";
    {
        std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
        if (!file) throw std::runtime_error("provider_federation_output_open_failed");
        file << output.dump(2) << '\n';
        if (!file) throw std::runtime_error("provider_federation_output_write_failed");
    }
    std::filesystem::rename(temporary, target);
}
}

int main(int argc, char** argv) {
    if (argc > 2) {
        std::cerr << "Usage: provider_federation_probe [output.json|-]\n";
        return EXIT_FAILURE;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        std::cerr << "provider_federation_curl_init_failed\n";
        return EXIT_FAILURE;
    }
    try {
        const auto output = cfss::federation::collect_market_wide_provider_federation();
        write_output(argc == 2 ? argv[1] : "-", output);
        const bool pass = output.value("status", std::string{}) ==
            "TWO_FRESH_LICENSE_ELIGIBLE_PROVIDERS_FULL_NINE_ASSET_MATCH";
        curl_global_cleanup();
        return pass ? EXIT_SUCCESS : 2;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "provider_federation_probe_failed:" << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
