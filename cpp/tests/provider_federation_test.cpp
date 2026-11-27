#include "cfss/provider_federation.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>

using cfss::federation::json;

int main() {
    const json cmc_fixture = {
        {"data", json::array({
            {
                {"id", 1}, {"name", "Bitcoin"}, {"symbol", "BTC"}, {"cmc_rank", 1},
                {"quote", {{"USD", {
                    {"price", 100000.0}, {"market_cap", 2000000000000.0},
                    {"volume_24h", 30000000000.0}, {"last_updated", "2026-11-27T00:00:00.000Z"}
                }}}}
            },
            {
                {"id", 1027}, {"name", "Ethereum"}, {"symbol", "ETH"}, {"cmc_rank", 2},
                {"quote", {{"USD", {
                    {"price", "3000.0"}, {"market_cap", "360000000000.0"},
                    {"volume_24h", "12000000000.0"}, {"last_updated", "2026-11-27T00:00:00.000Z"}
                }}}}
            }
        })}
    };

    const json paprika_fixture = json::array({
        {
            {"id", "btc-bitcoin"}, {"name", "Bitcoin"}, {"symbol", "BTC"}, {"rank", 1},
            {"last_updated", "2026-11-27T00:00:02Z"},
            {"quotes", {{"USD", {
                {"price", 100020.0}, {"market_cap", 2001000000000.0},
                {"volume_24h", 30100000000.0}
            }}}}
        },
        {
            {"id", "eth-ethereum"}, {"name", "Ethereum"}, {"symbol", "ETH"}, {"rank", 2},
            {"last_updated", "2026-11-27T00:00:02Z"},
            {"quotes", {{"USD", {
                {"price", 3001.0}, {"market_cap", 360100000000.0},
                {"volume_24h", 12100000000.0}
            }}}}
        }
    });

    const auto cmc = cfss::federation::parse_coinmarketcap(cmc_fixture);
    const auto paprika = cfss::federation::parse_coinpaprika(paprika_fixture);
    if (cmc.size() != 2U || paprika.size() != 2U) {
        std::cerr << "provider fixture parsing count failed\n";
        return EXIT_FAILURE;
    }
    if (cmc[0].provider_id != "coinmarketcap" || cmc[0].provider_asset_id != "1" ||
        cmc[0].symbol != "BTC" || std::abs(cmc[1].price_usd - 3000.0) > 1e-9) {
        std::cerr << "CoinMarketCap normalization failed\n";
        return EXIT_FAILURE;
    }
    if (paprika[0].provider_id != "coinpaprika" || paprika[0].provider_asset_id != "btc-bitcoin" ||
        paprika[0].symbol != "BTC" || std::abs(paprika[1].volume_24h_usd - 12100000000.0) > 1e-3) {
        std::cerr << "CoinPaprika normalization failed\n";
        return EXIT_FAILURE;
    }

    cfss::federation::ProviderSnapshot cmc_snapshot{
        "coinmarketcap", "LIVE", "2026-11-27T00:00:03Z", 200, "", cmc
    };
    cfss::federation::ProviderSnapshot paprika_snapshot{
        "coinpaprika", "LIVE", "2026-11-27T00:00:03Z", 200, "", paprika
    };
    const auto references = cfss::federation::compare_candidate_references(
        cmc_snapshot, paprika_snapshot,
        {
            {"bitcoin", "BTC", "1", "btc-bitcoin"},
            {"ethereum", "ETH", "1027", "eth-ethereum"},
            {"solana", "SOL", "5426", "sol-solana"}
        }
    );
    if (references.size() != 3U ||
        references[0].classification != "REAL_MULTI_SOURCE" ||
        references[1].classification != "REAL_MULTI_SOURCE" ||
        references[2].classification != "UNAVAILABLE") {
        std::cerr << "provider identity matching/classification failed\n";
        return EXIT_FAILURE;
    }
    if (!(references[0].price_difference_bps > 0.0 &&
          references[0].price_difference_bps < 10.0)) {
        std::cerr << "cross-provider price discrepancy calculation failed\n";
        return EXIT_FAILURE;
    }

    auto paprika_missing = paprika_snapshot;
    paprika_missing.tickers.erase(paprika_missing.tickers.begin());
    const auto single = cfss::federation::compare_candidate_references(
        cmc_snapshot, paprika_missing, {{"bitcoin", "BTC", "1", "btc-bitcoin"}});
    if (single.size() != 1U || single[0].classification != "REAL_SINGLE_SOURCE") {
        std::cerr << "single-source honesty classification failed\n";
        return EXIT_FAILURE;
    }

    bool invalid_cmc_rejected = false;
    try {
        (void)cfss::federation::parse_coinmarketcap(json::array());
    } catch (const std::invalid_argument&) {
        invalid_cmc_rejected = true;
    }
    bool invalid_paprika_rejected = false;
    try {
        (void)cfss::federation::parse_coinpaprika(json::object());
    } catch (const std::invalid_argument&) {
        invalid_paprika_rejected = true;
    }
    if (!invalid_cmc_rejected || !invalid_paprika_rejected) {
        std::cerr << "invalid provider response shape was not rejected\n";
        return EXIT_FAILURE;
    }

    std::cout << "PROVIDER_FEDERATION_CONTRACT_TESTS_PASS\n";
    return EXIT_SUCCESS;
}
