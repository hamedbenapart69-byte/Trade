#include "cfss/lfs.hpp"
#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {
using cfss::lfs::Component;
using cfss::lfs::DataClass;
using cfss::lfs::aggregate_v1;
using cfss::lfs::component_ids;

std::array<Component, 5> complete(DataClass kind = DataClass::REAL) {
    std::array<Component, 5> rows{};
    for (std::size_t i = 0; i < rows.size(); ++i) {
        rows[i] = {std::string(component_ids[i]), 0.5, kind, 1000, "test-definition-v1"};
    }
    return rows;
}

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    auto rows = complete();
    const auto baseline = aggregate_v1(rows, 2000);
    require(baseline.status == "CALCULATED", "complete valid components calculate");
    require(baseline.score.has_value() && std::abs(*baseline.score - 0.5) < 1e-12,
            "weights sum to one and preserve equal component scores");
    require(baseline.data_class == "REAL", "all-real components remain REAL");

    rows[2].score.reset();
    const auto missing = aggregate_v1(rows, 2000);
    require(missing.status == "UNAVAILABLE" && !missing.score.has_value(),
            "missing component blocks aggregate");
    require(missing.missing_count == 1U, "missing component is named");
    require(missing.real_count == 4U, "coverage count is retained");

    rows = complete(DataClass::PROXY);
    const auto proxy = aggregate_v1(rows, 2000);
    require(proxy.status == "CALCULATED" && proxy.data_class == "PROXY",
            "proxy provenance is preserved");

    rows = complete();
    rows[0].score = 1.01;
    require(aggregate_v1(rows, 2000).status == "UNAVAILABLE",
            "out-of-range score is rejected");

    rows = complete();
    rows[1].available_at_ms = 2001;
    require(aggregate_v1(rows, 2000).status == "UNAVAILABLE",
            "future availability is rejected");

    rows = complete();
    rows[4].definition_id.clear();
    require(aggregate_v1(rows, 2000).status == "UNAVAILABLE",
            "undefined component formula is rejected");

    std::cout << "LFS_V1_CONTRACT_TESTS_PASS\n";
    return 0;
}
