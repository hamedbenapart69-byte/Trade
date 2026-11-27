#include "cfss/provider_federation.hpp"

#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <chrono>
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
        auto cmc = cfss::federation::fetch_coinmarketcap();
        auto gecko = cfss::federation::ProviderSnapshot{
            "coingecko", "DISABLED_BY_JURISDICTION_POLICY", cfss::federation::utc_now_iso(),
            0, "excluded_country_policy_applies_to_IR", "disabled_without_request",
            "UNAVAILABLE", "EXCLUDED_COUNTRY_IR", 0, {}
        };
        auto ranking = cfss::federation::fetch_coinranking();
        auto paprika = cfss::federation::fetch_coinpaprika();

        const auto& identities = cfss::federation::candidate_identity_seed();
        const auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        cfss::federation::evaluate_snapshot_freshness(cmc, identities, now_ms, 15LL * 60LL * 1000LL);
        cfss::federation::evaluate_snapshot_freshness(ranking, identities, now_ms, 15LL * 60LL * 1000LL);
        cfss::federation::evaluate_snapshot_freshness(paprika, identities, now_ms, 15LL * 60LL * 1000LL);

        const auto ranking_paprika =
            cfss::federation::compare_coinranking_coinpaprika_references(ranking, paprika);

        json candidate_rows = json::array();
        bool btc_two_source_match = false;
        std::size_t matched_asset_count = 0U;
        for (std::size_t i = 0; i < identities.size(); ++i) {
            const auto& selected = ranking_paprika[i];
            const bool matched = selected.classification == "TWO_SOURCE_IDENTITY_MATCHED";
            if (matched) ++matched_asset_count;
            if (identities[i].canonical_symbol == "BTC" && matched) btc_two_source_match = true;
            candidate_rows.push_back({
                {"canonical_asset_id", identities[i].canonical_asset_id},
                {"canonical_symbol", identities[i].canonical_symbol},
                {"classification", selected.classification},
                {"matched_provider_pair", matched ? "coinranking+coinpaprika" : "NONE"}
            });
        }

        const int live_provider_count =
            (cmc.status == "LIVE_RESPONSE_PARSED" ? 1 : 0) +
            (ranking.status == "LIVE_RESPONSE_PARSED" ? 1 : 0) +
            (paprika.status == "LIVE_RESPONSE_PARSED" ? 1 : 0);
        // CMC keyless is evaluation-only; CoinGecko is jurisdiction-blocked.
        const int production_eligible_fresh_provider_count =
            (ranking.freshness_status == "FRESH" &&
             ranking.license_status == "PERSONAL_INTERNAL_USE_FREE_PLAN" ? 1 : 0) +
            (paprika.freshness_status == "FRESH" &&
             paprika.license_status == "PERSONAL_USE_ONLY" ? 1 : 0);
        const bool federation_discovery_pass =
            production_eligible_fresh_provider_count >= 2 &&
            btc_two_source_match && matched_asset_count == identities.size();

        const json output = {
            {"document_version", "V21.1"},
            {"artifact_type", "cfss_provider_federation_discovery_v1"},
            {"generated_at_utc", cfss::federation::utc_now_iso()},
            {"run_status", federation_discovery_pass
                ? "TWO_FRESH_LICENSE_ELIGIBLE_PROVIDERS_FULL_NINE_ASSET_MATCH"
                : "PROVIDER_DISCOVERY_PARTIAL"},
            {"production_universe_status", "DISCOVERY_ONLY_NOT_FROZEN"},
            {"live_provider_count", live_provider_count},
            {"production_eligible_fresh_provider_count", production_eligible_fresh_provider_count},
            {"matched_asset_count", matched_asset_count},
            {"required_asset_count", identities.size()},
            {"providers", json::array({
                cfss::federation::snapshot_health_to_json(cmc),
                cfss::federation::snapshot_health_to_json(gecko),
                cfss::federation::snapshot_health_to_json(ranking),
                cfss::federation::snapshot_health_to_json(paprika)
            })},
            {"candidate_seed", candidate_rows},
            {"limitations", json::array({
                "CoinGecko is disabled: the published excluded-country list includes Iran; HTTP reachability does not override license restrictions.",
                "Coinranking free tier requires COINRANKING_API_KEY and is limited to internal personal use; no raw data is redistributed.",
                "CoinPaprika free API is personal-use only; no raw ticker payload is redistributed.",
                "CoinMarketCap keyless endpoint is evaluation-only and is not counted toward production provider acceptance.",
                "CoinMarketCap and CoinRanking free API account eligibility from the user's jurisdiction must be respected; no access restrictions are bypassed.",
                "Raw provider ticker payloads and absolute market metrics are not emitted to public workflow logs.",
                "Market-wide spot references are not perpetual contract prices.",
                "This probe does not provide futures OHLCV, funding, open interest or order-book depth.",
                "The nine-asset candidate seed is provisional and is not a frozen production universe.",
                "Provider overlap by itself is not evidence of executable liquidity or a trading edge."
            })}
        };

        write_output(argc == 2 ? argv[1] : "-", output);
        curl_global_cleanup();
        return federation_discovery_pass ? EXIT_SUCCESS : 2;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "provider_federation_probe_failed:" << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
