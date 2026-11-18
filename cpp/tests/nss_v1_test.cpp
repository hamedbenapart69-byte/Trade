#include "cfss/nss.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string>

namespace {
void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

std::array<cfss::nss::Component, 5> complete_components() {
    using cfss::nss::Component;
    using cfss::nss::DataClass;
    return {{
        { "NSS1_OPEN_INTEREST_GROWTH", 0.80, DataClass::REAL, 1000, "nss1_v1_contract" },
        { "NSS2_HEALTHY_FUNDING", 0.60, DataClass::REAL, 1000, "nss2_v1_contract" },
        { "NSS3_BASIS_EXPANSION", 0.70, DataClass::REAL, 1000, "nss3_v1_contract" },
        { "NSS4_VOLUME_EXPANSION", 0.90, DataClass::REAL, 1000, "nss4_v1_contract" },
        { "NSS5_PRE_BREAKOUT_COMPRESSION", 0.50, DataClass::REAL, 1000, "nss5_v1_contract" }
    }};
}
}

int main() {
    using cfss::nss::DataClass;
    auto components = complete_components();
    const auto result = cfss::nss::aggregate_v1(components, 1000);
    require(result.status == "CALCULATED" && result.score.has_value(),
            "five valid REAL components produce a score");
    require(std::abs(*result.score - 0.71) < 1e-12,
            "canonical NSS weights are applied without redistribution");

    auto missing = components;
    missing[2].score.reset();
    const auto missing_result = cfss::nss::aggregate_v1(missing, 1000);
    require(missing_result.status == "UNAVAILABLE" && missing_result.missing_count == 1U,
            "missing basis score blocks full NSS");

    auto proxy = components;
    proxy[0].data_class = DataClass::PROXY;
    require(cfss::nss::aggregate_v1(proxy, 1000).status == "UNAVAILABLE",
            "v1 rejects PROXY inputs");

    auto future = components;
    future[4].available_at_ms = 1001;
    require(cfss::nss::aggregate_v1(future, 1000).status == "UNAVAILABLE",
            "future component is rejected");

    auto out_of_range = components;
    out_of_range[1].score = 1.01;
    require(cfss::nss::aggregate_v1(out_of_range, 1000).status == "UNAVAILABLE",
            "scores outside [0,1] are rejected");

    auto wrong_order = components;
    wrong_order[0].id = "NSS2_HEALTHY_FUNDING";
    require(cfss::nss::aggregate_v1(wrong_order, 1000).status == "UNAVAILABLE",
            "component identity and order are enforced");

    std::cout << "NSS_V1_CONTRACT_TESTS_PASS\n";
    return 0;
}
