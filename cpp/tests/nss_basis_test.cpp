#include "cfss/nss_basis.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    using nlohmann::json;
    const json perp = json::array({
        {{"timestamp_ms", 1000}, {"close", 101.0}},
        {{"timestamp_ms", 2000}, {"close", 102.0}},
        {{"timestamp_ms", 3000}, {"close", 103.0}}
    });
    const json spot = json::array({
        {{"timestamp_ms", 1000}, {"close", 100.0}},
        {{"timestamp_ms", 2000}, {"close", 100.0}},
        {{"timestamp_ms", 3000}, {"close", 100.0}}
    });
    const auto basis = cfss::nss::build_basis_series(perp, spot, 2000);
    require(basis.size() == 2U, "future spot/perpetual rows are excluded");
    require(std::abs(basis[0].at("basis_bps").get<double>() - 100.0) < 1e-12,
            "one percent premium equals 100 basis points");
    require(basis[0].at("source_quality") == "REAL",
            "spot/perpetual close basis retains REAL source quality");
    const auto empty = cfss::nss::build_basis_series(perp, json::array(), 3000);
    require(empty.empty(), "missing spot series does not fabricate basis");
    std::cout << "NSS_BASIS_TESTS_PASS\n";
    return 0;
}
