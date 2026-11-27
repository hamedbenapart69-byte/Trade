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
                {"quote", json::array({{
                    {"symbol", "USD"}, {"price", 100000.0}, {"market_cap", 2000000000000.0},
                    {"volume_24h", 30000000000.0}, {"last_updated", "2026-11-27T00:00:00.000Z"}
                }})}
            },
            {
                {"id", 1027}, {"name", "Ethereum"}, {"symbol", "ETH"}, {"cmc_rank", 2},
                {"quote", json::array({{
                    {"symbol", "USD"}, {"price", "3000.0"}, {"market_cap", "360000000000.0"},
                    {"volume_24h", "12000000000.0"}, {"last_updated", "2026-11-27T00:00:00.000Z"}
                }})}
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

    const json gecko_fixture = json::array({
        {
            {"id", "bitcoin"}, {"symbol", "btc"}, {"name", "Bitcoin"}, {"market_cap_rank", 1},
            {"current_price", 100010.0}, {"market_cap", 2000500000000.0},
            {"total_volume", 30050000000.0}, {"last_updated", "2026-11-27T00:00:01Z"}
        },
        {
            {"id", "ethereum"}, {"symbol", "eth"}, {"name", "Ethereum"}, {"market_cap_rank", 2},
            {"current_price", 3002.0}, {"market_cap", 360200000000.0},
            {"total_volume", 12150000000.0}, {"last_updated", "2026-11-27T00:00:01Z"}
        }
    });

    const json cmc_quotes_fixture = {
        {"data", {
            {"1", {
                {"id", 1}, {"name", "Bitcoin"}, {"symbol", "BTC"}, {"cmc_rank", 1},
                {"quote", json::array({{
                    {"symbol", "USD"}, {"price", 100000.0}, {"market_cap", 2000000000000.0},
                    {"volume_24h", 30000000000.0}, {"last_updated", "2026-11-27T00:00:00.000Z"}
                }})}
            }}
        }}
    };

    const auto cmc = cfss::federation::parse_coinmarketcap(cmc_fixture);
    const auto cmc_quotes = cfss::federation::parse_coinmarketcap(cmc_quotes_fixture);
    if (cmc_quotes.size() != 1U || cmc_quotes[0].provider_asset_id != "1" ||
        cmc_quotes[0].symbol != "BTC") {
        std::cerr << "CoinMarketCap quotes/latest object envelope parsing failed\n";
        return EXIT_FAILURE;
    }
    const auto paprika = cfss::federation::parse_coinpaprika(paprika_fixture);
    const auto gecko = cfss::federation::parse_coingecko(gecko_fixture);
    if (cmc.size() != 2U || paprika.size() != 2U || gecko.size() != 2U) {
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
        "coinmarketcap", "LIVE_RESPONSE_PARSED", "2026-11-27T00:00:03Z", 200, "", "listings_latest", "NOT_TESTED", "NOT_VERIFIED", 1, cmc
    };
    if (gecko[0].provider_id != "coingecko" || gecko[0].provider_asset_id != "bitcoin" ||
        gecko[0].symbol != "BTC" || std::abs(gecko[1].price_usd - 3002.0) > 1e-9) {
        std::cerr << "CoinGecko normalization failed\n";
        return EXIT_FAILURE;
    }
    cfss::federation::ProviderSnapshot gecko_snapshot{
        "coingecko", "LIVE_RESPONSE_PARSED", "2026-11-27T00:00:03Z", 200, "", "coins_markets", "NOT_TESTED", "NOT_VERIFIED", 1, gecko
    };
    cfss::federation::ProviderSnapshot paprika_snapshot{
        "coinpaprika", "LIVE_RESPONSE_PARSED", "2026-11-27T00:00:03Z", 200, "", "tickers", "NOT_TESTED", "NOT_VERIFIED", 1, paprika
    };
    const auto references = cfss::federation::compare_candidate_references(
        cmc_snapshot, paprika_snapshot,
        {
            {"bitcoin", "BTC", "1", "bitcoin", "btc-bitcoin"},
            {"ethereum", "ETH", "1027", "ethereum", "eth-ethereum"},
            {"solana", "SOL", "5426", "solana", "sol-solana"}
        }
    );
    if (references.size() != 3U ||
        references[0].classification != "TWO_SOURCE_IDENTITY_MATCHED" ||
        references[1].classification != "TWO_SOURCE_IDENTITY_MATCHED" ||
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
        cmc_snapshot, paprika_missing, {{"bitcoin", "BTC", "1", "bitcoin", "btc-bitcoin"}});
    if (single.size() != 1U || single[0].classification != "ONE_SOURCE_IDENTITY_MATCHED") {
        std::cerr << "single-source honesty classification failed\n";
        return EXIT_FAILURE;
    }

    const auto cmc_gecko = cfss::federation::compare_cmc_coingecko_references(
        cmc_snapshot, gecko_snapshot,
        {
            {"bitcoin", "BTC", "1", "bitcoin", "btc-bitcoin"},
            {"ethereum", "ETH", "1027", "ethereum", "eth-ethereum"},
            {"solana", "SOL", "5426", "solana", "sol-solana"}
        }
    );
    if (cmc_gecko.size() != 3U ||
        cmc_gecko[0].classification != "TWO_SOURCE_IDENTITY_MATCHED" ||
        cmc_gecko[0].coingecko_price_usd != 100010.0 ||
        cmc_gecko[2].classification != "UNAVAILABLE") {
        std::cerr << "CoinMarketCap/CoinGecko independent reference comparison failed\n";
        return EXIT_FAILURE;
    }

    const auto gecko_paprika = cfss::federation::compare_coingecko_coinpaprika_references(
        gecko_snapshot, paprika_snapshot,
        {
            {"bitcoin", "BTC", "1", "bitcoin", "btc-bitcoin"},
            {"ethereum", "ETH", "1027", "ethereum", "eth-ethereum"},
            {"solana", "SOL", "5426", "solana", "sol-solana"}
        }
    );
    if (gecko_paprika.size() != 3U ||
        gecko_paprika[0].classification != "TWO_SOURCE_IDENTITY_MATCHED" ||
        gecko_paprika[0].coingecko_price_usd != 100010.0 ||
        gecko_paprika[2].classification != "UNAVAILABLE") {
        std::cerr << "CoinGecko/CoinPaprika independent fallback comparison failed\n";
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

    cfss::federation::ProviderCapabilityRegistry registry;
    registry.add({"coinmarketcap", "price", "SPOT_REFERENCE", "USD/asset", "USD",
                   {"BTC", "ETH"}, 900000, 365, "COMPATIBLE", "REACHABLE"});
    registry.add({"coingecko", "price", "SPOT_REFERENCE", "USD/asset", "USD",
                   {"BTC", "ETH"}, 900000, 365, "COMPATIBLE", "REACHABLE"});
    registry.add({"venue-x", "open_interest", "PERPETUAL", "contracts", "USDT",
                   {"BTC"}, 10800000, 30, "COMPATIBLE", "REACHABLE"});
    const auto spot_sources = registry.eligible("price", "SPOT_REFERENCE", "BTC");
    const auto oi_sources = registry.eligible("open_interest", "PERPETUAL", "BTC");
    const auto unsupported_sources = registry.eligible("open_interest", "SPOT_REFERENCE", "BTC");
    if (spot_sources.size() != 2U || oi_sources.size() != 1U || !unsupported_sources.empty()) {
        std::cerr << "field-level provider capability routing failed\n";
        return EXIT_FAILURE;
    }

    const cfss::federation::CanonicalRecord required{
        "bitcoin", "BTC", "venue-a", "BTC-USDT-SWAP", "PERPETUAL", "open_interest",
        1000.0, "contracts", "USDT", "1h", 1795737600000LL, 1795737600000LL,
        1795737605000LL, "VALID", "REAL", "COMPATIBLE"
    };
    auto compatible = required;
    compatible.provider_id = "venue-b";
    compatible.provider_instrument_id = "XBTUSDTM";
    if (!cfss::federation::fallback_compatible(required, compatible, 1795737610000LL, 900000LL)) {
        std::cerr << "valid same-field fallback was rejected\n";
        return EXIT_FAILURE;
    }
    auto same_provider = compatible;
    same_provider.provider_id = required.provider_id;
    auto incompatible_scope = compatible;
    incompatible_scope.market_scope = "SPOT";
    auto incompatible_unit = compatible;
    incompatible_unit.unit = "USD";
    auto proxy_fallback = compatible;
    proxy_fallback.data_class = "PROXY";
    auto stale_fallback = compatible;
    stale_fallback.provider_timestamp_ms = 1795730000000LL;
    if (cfss::federation::fallback_compatible(required, same_provider, 1795737610000LL, 900000LL) ||
        cfss::federation::fallback_compatible(required, incompatible_scope, 1795737610000LL, 900000LL) ||
        cfss::federation::fallback_compatible(required, incompatible_unit, 1795737610000LL, 900000LL) ||
        cfss::federation::fallback_compatible(required, proxy_fallback, 1795737610000LL, 900000LL) ||
        cfss::federation::fallback_compatible(required, stale_fallback, 1795737610000LL, 900000LL)) {
        std::cerr << "incompatible or proxy fallback was accepted\n";
        return EXIT_FAILURE;
    }

    std::cout << "PROVIDER_FEDERATION_CONTRACT_TESTS_PASS\n";
    return EXIT_SUCCESS;
}
