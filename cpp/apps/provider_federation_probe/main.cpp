#include "cfss/provider_federation.hpp"

#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <cstdlib>
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
        const auto cmc = cfss::federation::fetch_coinmarketcap();
        const auto gecko = cfss::federation::fetch_coingecko();
        const auto references = cfss::federation::compare_cmc_coingecko_references(cmc, gecko);

        json candidate_rows = json::array();
        for (const auto& item : references) {
            candidate_rows.push_back({
                {"canonical_asset_id", item.canonical_asset_id},
                {"canonical_symbol", item.canonical_symbol},
                {"classification", item.classification},
            });
        }

        const bool both_live = cmc.status == "LIVE_RESPONSE_PARSED" && gecko.status == "LIVE_RESPONSE_PARSED";
        const json output = {
            {"document_version", "V21.1"},
            {"artifact_type", "cfss_provider_federation_discovery_v1"},
            {"generated_at_utc", cfss::federation::utc_now_iso()},
            {"run_status", both_live ? "TWO_PROVIDER_LIVE_RESPONSE_PARSED_FRESHNESS_UNVERIFIED" : "PROVIDER_DISCOVERY_PARTIAL"},
            {"production_universe_status", "DISCOVERY_ONLY_NOT_FROZEN"},
            {"providers", json::array({
                cfss::federation::snapshot_health_to_json(cmc),
                cfss::federation::snapshot_health_to_json(gecko)
            })},
            {"candidate_seed", candidate_rows},
            {"limitations", json::array({
                "CoinGecko Public API rate limit is variable; this probe performs only one bounded request per scan.",
                "Provider license and public-artifact redistribution compatibility remain NOT_VERIFIED until reviewed.",
                "Raw provider ticker payloads and absolute market metrics are not emitted to public workflow logs.",
                "Market-wide spot references are not perpetual contract prices.",
                "This probe does not provide futures OHLCV, funding, open interest or order-book depth.",
                "The nine-asset candidate seed is provisional and is not a frozen production universe.",
                "Provider overlap by itself is not evidence of executable liquidity or a trading edge."
            })}
        };

        write_output(argc == 2 ? argv[1] : "-", output);
        curl_global_cleanup();
        return both_live ? EXIT_SUCCESS : 2;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "provider_federation_probe_failed:" << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
