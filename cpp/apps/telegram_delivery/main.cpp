#include "cfss/telegram_l3.hpp"
#include "cfss/hash.hpp"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "Usage: telegram_delivery <l2-artifact.json> <outbox-state.json> <run-manifest.json>\n";
        return EXIT_FAILURE;
    }
    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    if (!token || !chat_id || token[0] == '\0' || chat_id[0] == '\0') {
        std::cerr << "TELEGRAM_CONFIGURATION_MISSING\n";
        return EXIT_FAILURE;
    }
    bool curl_ready = curl_global_init(CURL_GLOBAL_DEFAULT) == CURLE_OK;
    if (!curl_ready) return EXIT_FAILURE;
    try {
        std::ifstream input(argv[1], std::ios::binary);
        if (!input) throw std::runtime_error("l2_artifact_open_failed");
        const std::string raw{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
        const auto artifact = nlohmann::json::parse(raw);
        if (!cfss::verify_artifact_hash(artifact))
            throw std::runtime_error("l2_artifact_sha256_verification_failed");
        const int result = cfss::telegram::run_outbound(artifact, argv[2], token, chat_id);
        cfss::telegram::record_outbound_manifest(argv[3], argv[2], artifact.at("source_scan_id").get<std::string>());
        curl_global_cleanup();
        return result;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "TELEGRAM_OUTBOUND_FAILED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
